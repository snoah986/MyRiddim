"""Local YouTube Music API bridge."""
from pathlib import Path
import json
import os
import tempfile
import sqlite3
import re
import hashlib
import math
import socket
import threading
import time
import traceback
import urllib.parse
import urllib.request
import urllib.error
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, jsonify, request, send_file, send_from_directory, Response, stream_with_context
from flask_cors import CORS

try:
    from .matcher import backfill_listens, ingest_track
    from .providers.soundcloud import SoundCloudProvider
    from .radio import normalize_radio_tracks
    from .party import PARTY_STORE, PartyStore
    from .lyrics_yrc import build_cadence_lines, fetch_netease_yrc
except ImportError:
    from matcher import backfill_listens, ingest_track
    from providers.soundcloud import SoundCloudProvider
    from radio import normalize_radio_tracks
    from party import PARTY_STORE, PartyStore
    from lyrics_yrc import build_cadence_lines, fetch_netease_yrc

app = Flask(__name__)

# The desktop player is the source of truth. Remote clients enqueue commands
# here, while the desktop frontend polls and acknowledges them. Keeping this
# state in memory makes the remote responsive without persisting playback data
# or credentials.
REMOTE_LOCK = threading.RLock()
REMOTE_STATE = {
    "current_track": None,
    "is_playing": False,
    "current_time": 0.0,
    "duration": 0.0,
    "volume": 1.0,
    "shuffle": False,
    "repeat": "off",
    "queue": [],
    "lyrics": [],
    "updated_at": 0.0,
}
REMOTE_COMMANDS = []
REMOTE_COMMAND_ID = 0
REMOTE_COMMAND_TTL = 60
REMOTE_ACTIONS = {"toggle_play", "previous", "next", "seek", "set_volume",
                  "toggle_shuffle", "toggle_repeat", "play_track"}


def prune_remote_commands(now=None):
    now = time.time() if now is None else now
    cutoff = now - REMOTE_COMMAND_TTL
    REMOTE_COMMANDS[:] = [command for command in REMOTE_COMMANDS
                          if command.get("created_at", now) >= cutoff]

# The app holds the user's real Google session cookies, so only the local
# frontend/backend origins may read responses. A wildcard here would let any
# website loaded in the browser silently read localhost API responses.
CORS(app, origins=[
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5178", "http://127.0.0.1:5178",
    "http://tauri.localhost", "https://tauri.localhost",
] + [origin.strip().rstrip('/') for origin in os.getenv('YTM_CORS_ORIGINS', '').split(',') if origin.strip()])

ROOT = Path(__file__).resolve().parent.parent


@app.get("/api/party/state")
def party_state():
    """Full party snapshot for the host UI (and guest sync via ?code=)."""
    code = clean(request.args.get("code"))
    room = PARTY_STORE.get_room(code) if code else None
    if not room:
        return jsonify({"active": False})
    return jsonify({"active": True, **room.public_state()})


@app.post("/api/party/create")
def party_create():
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.create_room(clean(data.get("host_name")) or "Host")
    settings = data.get("settings")
    if isinstance(settings, dict):
        PartyStore.update_settings(room, settings)
    return jsonify({"code": room.code, "invite_url": party_invite_url(room.code), **room.public_state()}), 201


def _lan_ip():
    """Best-effort LAN address guests can reach (UDP connect probes the route
    without sending packets). Falls back to localhost when offline."""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        try:
            if sock:
                sock.close()
        except OSError:
            pass


def party_invite_url(code):
    port = os.getenv("YTM_BACKEND_PORT", "5178")
    return f"http://{_lan_ip()}:{port}/mobile?party={code}"


@app.post("/api/party/close")
def party_close():
    data = request.get_json(silent=True) or {}
    closed = PARTY_STORE.close_room(clean(data.get("code")))
    if not closed:
        return jsonify({"error": "Room not found"}), 404
    return jsonify({"success": True})


def _party_room_and_guest():
    """Shared guard: resolve room + guest, touch liveness. Returns (room, guest, error_response)."""
    code = clean(request.args.get("code") or (request.get_json(silent=True) or {}).get("code"))
    guest_id = clean(request.args.get("guest_id") or (request.get_json(silent=True) or {}).get("guest_id"))
    room = PARTY_STORE.get_room(code)
    if not room:
        return None, None, (jsonify({"error": "Room not found"}), 404)
    guest = PartyStore.touch(room, guest_id) if guest_id else None
    if not guest:
        return room, None, (jsonify({"error": "Unknown guest — rejoin the party", "rejoin": True}), 401)
    return room, guest, None


@app.post("/api/party/join")
def party_join():
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    guest = PartyStore.join(room, clean(data.get("name")))
    return jsonify({"guest_id": guest.id, "name": guest.name, **room.public_state()}), 201


@app.get("/api/party/queue")
def party_queue_for_guest():
    room, guest, error = _party_room_and_guest()
    if error:
        return error
    return jsonify({
        "guest": guest.to_dict(),
        "remaining_cooldown": room.remaining_cooldown(guest),
        "unplayed_count": room.unplayed_count(guest.id),
        "quota": room.settings["max_unplayed_per_guest"] if room.settings["max_unplayed_per_guest"] else None,
        **room.public_state(),
    })


@app.post("/api/party/request")
def party_request_track():
    """A guest asks for a track. Returns playback commands when auto-approved."""
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    guest = PartyStore.touch(room, clean(data.get("guest_id")))
    if not guest:
        return jsonify({"error": "Unknown guest — rejoin the party", "rejoin": True}), 401
    track = data.get("track")
    if not isinstance(track, dict):
        return jsonify({"error": "Track must be an object"}), 400
    entry, error = PartyStore.request_track(room, guest, track)
    if error:
        return jsonify({"error": error, "remaining_cooldown": room.remaining_cooldown(guest)}), 429
    commands = []
    if entry["status"] == "queued":
        commands = [{"action": "add_to_queue", "payload": {
            "videoId": entry["videoId"], "title": entry["title"], "artist": entry["artist"],
            "thumbnail": entry["thumbnail"], "duration": entry["duration"],
            "requested_by": entry.get("requested_by"), "priority": entry.get("priority", False),
        }}]
        # Party transitions must stay gapless: start buffering the audio the
        # moment a request is auto-approved.
        download_to_cache(entry["videoId"], auth_headers())
    return jsonify({"entry": entry, "commands": commands, **room.public_state()}), 201


@app.post("/api/party/vote")
def party_vote():
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    guest = PartyStore.touch(room, clean(data.get("guest_id")))
    if not guest:
        return jsonify({"error": "Unknown guest — rejoin the party", "rejoin": True}), 401
    votes = PartyStore.upvote(room, clean(data.get("video_id")), guest)
    if votes is None:
        return jsonify({"error": "Voting not allowed for your role"}), 403
    return jsonify({"votes": votes, **room.public_state()})


@app.post("/api/party/approve")
def party_approve():
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    entry = PartyStore.approve(room, clean(data.get("video_id")))
    if not entry:
        return jsonify({"error": "Nothing to approve"}), 404
    commands = [{"action": "add_to_queue", "payload": {
        "videoId": entry["videoId"], "title": entry["title"], "artist": entry["artist"],
        "thumbnail": entry["thumbnail"], "duration": entry["duration"],
        "requested_by": entry.get("requested_by"), "priority": entry.get("priority", False),
    }}]
    # Approved tracks join the live queue: pre-cache so the transition is gapless.
    download_to_cache(entry["videoId"], auth_headers())
    return jsonify({"entry": entry, "commands": commands, **room.public_state()})


@app.post("/api/party/reject")
def party_reject():
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    if not PartyStore.reject(room, clean(data.get("video_id"))):
        return jsonify({"error": "Nothing to reject"}), 404
    return jsonify({"success": True, **room.public_state()})


@app.post("/api/party/role")
def party_set_role():
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    if not PartyStore.set_role(room, clean(data.get("guest_id")), clean(data.get("role"))):
        return jsonify({"error": "Unknown guest or role"}), 404
    return jsonify({"success": True, **room.public_state()})


@app.post("/api/party/kick")
def party_kick():
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    if not PartyStore.kick(room, clean(data.get("guest_id"))):
        return jsonify({"error": "Unknown guest"}), 404
    return jsonify({"success": True, **room.public_state()})


@app.post("/api/party/settings")
def party_settings():
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    updates = data.get("settings")
    if not isinstance(updates, dict):
        return jsonify({"error": "settings must be an object"}), 400
    PartyStore.update_settings(room, updates)
    return jsonify({"success": True, **room.public_state()})


@app.post("/api/party/played")
def party_mark_played():
    """Host frontend reports the now-playing track so quotas/free the slot."""
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    PartyStore.mark_played(room, clean(data.get("video_id")))
    return jsonify({"success": True, **room.public_state()})


@app.post("/api/party/skip")
def party_vote_skip():
    """Guests vote to skip the current track; the host applies the returned
    command on its next state poll once half of connected guests have voted."""
    data = request.get_json(silent=True) or {}
    room = PARTY_STORE.get_room(clean(data.get("code")))
    if not room:
        return jsonify({"error": "Room not found"}), 404
    guest = PartyStore.touch(room, clean(data.get("guest_id")))
    if not guest:
        return jsonify({"error": "Unknown guest — rejoin the party", "rejoin": True}), 401
    result = PartyStore.vote_skip(room, guest)
    if result is None:
        return jsonify({"error": "Skip voting is not allowed"}), 403
    votes, threshold, requested = result
    return jsonify({"votes": votes, "threshold": threshold, "skip_requested": requested, **room.public_state()})


def _user_data_dir():
    """User-writable data directory OUTSIDE the project tree.

    Credentials and listening history live here so the repo can never leak
    them — even if .gitignore is edited, archived, or the folder is shared.
    Overridable via YTM_DATA_DIR (useful for the packaged desktop app).
    """
    override = os.environ.get("YTM_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ytm-player"


def _migrate_out_of_repo():
    """Move credentials/stats from their legacy in-repo locations to DATA_DIR.

    Runs once at startup; afterwards the project tree holds none of these files.
    """
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    legacy = {
        ROOT / "browser.json": DATA_DIR / "browser.json",
        Path(__file__).parent / "browser.json": DATA_DIR / "browser.json",
        ROOT / "oauth.json": DATA_DIR / "oauth.json",
        Path(__file__).parent / "oauth.json": DATA_DIR / "oauth.json",
        ROOT / "stats.db": DATA_DIR / "stats.db",
        Path(__file__).parent / "stats.db": DATA_DIR / "stats.db",
        Path(__file__).parent / "settings.json": DATA_DIR / "settings.json",
        ROOT / ".freebuff" / "library_cache.json": DATA_DIR / "library_cache.json",
    }
    for old, new in legacy.items():
        try:
            if old.is_file() and not new.exists():
                os.replace(old, new)
        except OSError:
            pass
    # Preserve any existing downloaded audio without moving the whole
    # .freebuff directory (which may also contain preview logs).
    old_cache = ROOT / ".freebuff" / "audio_cache"
    try:
        if old_cache.is_dir():
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            for old in old_cache.iterdir():
                new = CACHE_DIR / old.name
                if old.is_file() and not new.exists():
                    os.replace(old, new)
    except OSError:
        pass


DATA_DIR = _user_data_dir()
AUTH_PATH = DATA_DIR / "browser.json"
AUTH_CANDIDATES = [AUTH_PATH, DATA_DIR / "oauth.json"]
STATS_PATH = DATA_DIR / "stats.db"
OAUTH_CLIENT_PATH = DATA_DIR / "oauth_client.json"
# Runtime state must be writable in a packaged install and survive updates,
# so credentials, stats, cache metadata, and audio all live under DATA_DIR.
LIBRARY_CACHE_PATH = DATA_DIR / "library_cache.json"
CACHE_DIR = DATA_DIR / "audio_cache"
CACHE_LIMIT_BYTES = 1024 ** 3  # 1 GB default LRU ceiling
SETTINGS_PATH = DATA_DIR / "settings.json"
_migrate_out_of_repo()
DEFAULT_SETTINGS = {"cache_limit_bytes": CACHE_LIMIT_BYTES, "quality": "high"}
QUALITY_FORMATS = {
    "high": "bestaudio[ext=webm]/bestaudio[ext=m4a]/251/140/ba/b",
    "medium": "bestaudio[ext=m4a]/140/bestaudio/best",
    "low": "bestaudio[abr<=128]/140/bestaudio/best",
}

# ---------------------------------------------------------------------------
# Security: input validation, path safety, and rate limiting.
# This server holds Google session cookies, so every user-controlled value is
# validated before it reaches yt-dlp or the filesystem, and expensive YouTube
# calls are throttled so a frontend bug (or a hostile page) can't hammer the
# YouTube Music API and get the account temporarily IP-banned.
# ---------------------------------------------------------------------------
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CANONICAL_ID_RE = re.compile(r"^[a-f0-9]{64}$")
PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
BROWSE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,80}$")


def valid_video_id(value):
    """YouTube video IDs are exactly 11 chars from [A-Za-z0-9_-]."""
    return bool(value) and bool(VIDEO_ID_RE.match(str(value)))


def valid_canonical_id(value):
    return bool(value) and bool(CANONICAL_ID_RE.match(str(value)))


def valid_playlist_id(value):
    """Playlist/browse IDs are short base64url-ish strings (PL..., LM, WL...)."""
    return bool(value) and bool(PLAYLIST_ID_RE.match(str(value)))


def valid_browse_id(value):
    """Channel/album browse IDs (UC..., MPREb_...) are base64url-ish strings."""
    return bool(value) and bool(BROWSE_ID_RE.match(str(value)))


_rate_buckets = defaultdict(list)
_rate_lock = threading.Lock()


def rate_limit(name, limit, window):
    """Sliding-window per-IP limiter: at most `limit` calls per `window` seconds."""
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            key = (name, request.remote_addr or "local")
            now = time.monotonic()
            with _rate_lock:
                if len(_rate_buckets) > 2000:  # bound memory
                    _rate_buckets.clear()
                bucket = [t for t in _rate_buckets[key] if now - t < window]
                if len(bucket) >= limit:
                    _rate_buckets[key] = bucket
                    oldest = bucket[0]
                    return jsonify({"error": "Rate limit exceeded, try again shortly.",
                                    "retry_after": round(window - (now - oldest), 1)}), 429
                bucket.append(now)
                _rate_buckets[key] = bucket
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def load_settings():
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {**DEFAULT_SETTINGS, **data}
    except (OSError, json.JSONDecodeError):
        pass
    return dict(DEFAULT_SETTINGS)


def save_settings(data):
    merged = {**DEFAULT_SETTINGS, **data}
    try:
        SETTINGS_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    except OSError:
        pass
    return merged


SETTINGS = load_settings()


def init_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

init_cache_dir()

def cached_audio(video_id):
    """Return the cached audio file for a video, if one exists and is non-empty.

    Resolved paths are verified to stay inside the cache directory so a crafted
    video_id can never traverse out of it (defense in depth: routes already
    reject non-conforming IDs).
    """
    if not CACHE_DIR.is_dir():
        return None
    root = CACHE_DIR.resolve()
    for path in CACHE_DIR.glob(f"{clean(video_id)}.*"):
        try:
            if path.is_file() and path.stat().st_size > 0 and path.resolve().is_relative_to(root):
                return path
        except (OSError, ValueError):
            continue
    return None

def evict_cache():
    """LRU eviction: delete oldest (by atime) files until under the size limit."""
    limit = SETTINGS.get("cache_limit_bytes", CACHE_LIMIT_BYTES)
    try:
        files = sorted((p for p in CACHE_DIR.iterdir() if p.is_file()),
                       key=lambda p: p.stat().st_atime)
        total = sum(p.stat().st_size for p in files)
        for path in files:
            if total <= limit:
                break
            try:
                size = path.stat().st_size
                path.unlink(missing_ok=True)
                total -= size
            except OSError:
                pass
    except OSError:
        pass


def cache_info():
    """Current cache statistics: file count and total bytes (both spellings so
    the frontend contract can never drift again)."""
    files = [p for p in CACHE_DIR.iterdir() if p.is_file()] if CACHE_DIR.is_dir() else []
    size = sum(p.stat().st_size for p in files)
    return {"count": len(files), "size_bytes": size, "sizeBytes": size}

# Serialize background cache downloads (one at a time) and never start a second
# download for the same video. Without this, a queue auto-advance cascade spawns
# unbounded concurrent yt-dlp operations that trip YouTube rate limits and make
# every stream extraction fail with "Requested format is not available".
_cache_semaphore = threading.Semaphore(1)
_cache_inflight = set()
_cache_inflight_lock = threading.Lock()


def download_to_cache(video_id, headers):
    """Asynchronously persist the best standalone audio stream to the cache."""
    vid = clean(video_id)
    with _cache_inflight_lock:
        if vid in _cache_inflight or cached_audio(vid):
            return
        _cache_inflight.add(vid)

    def worker():
        try:
            with _cache_semaphore:
                import yt_dlp
                options = {
                    "format": "bestaudio/best",
                    "quiet": True, "no_warnings": True, "noplaylist": True,
                    "outtmpl": str(CACHE_DIR / f"{vid}.%(ext)s"),
                    # No Cookie header: cookies make some extractions return
                    # storyboard-only formats and the download fails.
                    "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
                }
                with yt_dlp.YoutubeDL(options) as downloader:
                    downloader.download([f"https://www.youtube.com/watch?v={vid}"])
                evict_cache()
                analyze_cached_audio(vid)
        except Exception as exc:
            print(f"Cache download failed for {vid}: {exc}", flush=True)
        finally:
            with _cache_inflight_lock:
                _cache_inflight.discard(vid)
    threading.Thread(target=worker, daemon=True).start()


def db_connection():
    connection = sqlite3.connect(STATS_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def analyze_cached_audio(video_id, file_path=None):
    """Extract audio features (BPM, energy, valence) for a cached track and
    store them alongside its listen history.

    Librosa is an optional dependency: when absent this is a silent no-op so
    the cache pipeline never breaks. Runs synchronously from the cache worker
    thread (already off the request path).
    """
    try:
        import librosa
        import numpy as np
    except ImportError:
        return  # optional analysis, skip silently
    path = file_path or cached_audio(video_id)
    if not path:
        return
    try:
        y, sr = librosa.load(str(path), sr=22050, duration=60, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        energy = float(np.mean(librosa.feature.rms(y=y)))
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
        features = {"bpm": round(float(tempo), 1), "energy": round(energy * 100, 2),
                    "valence": round(centroid / (sr / 2), 2)}
        with db_connection() as db:
            db.execute("UPDATE listens SET bpm = ?, energy = ?, valence = ? WHERE video_id = ?",
                       (features["bpm"], features["energy"], features["valence"], clean(video_id)))
    except Exception as exc:
        print(f"Audio analysis failed for {video_id}: {exc}", flush=True)


def init_stats_db():
    with db_connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS listens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            thumbnail_url TEXT,
            played_at_timestamp TEXT NOT NULL,
            listen_duration_seconds INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            bpm REAL,
            energy REAL,
            valence REAL,
            palette_json TEXT
        )""")
        # Migrate existing databases: add event/audio columns when missing.
        columns = {row[1] for row in db.execute("PRAGMA table_info(listens)").fetchall()}
        for column, definition in (("completed", "INTEGER NOT NULL DEFAULT 0"),
                                   ("skipped", "INTEGER NOT NULL DEFAULT 0"),
                                   ("bpm", "REAL"), ("energy", "REAL"), ("valence", "REAL"), ("palette_json", "TEXT")):
            if column not in columns:
                db.execute(f"ALTER TABLE listens ADD COLUMN {column} {definition}")
        db.execute("""CREATE TABLE IF NOT EXISTS smart_playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rules_json TEXT NOT NULL,
            track_limit INTEGER NOT NULL DEFAULT 50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS video_resolutions (
            audio_video_id TEXT PRIMARY KEY,
            music_video_id TEXT,
            title TEXT,
            artist TEXT,
            source TEXT NOT NULL,
            resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS video_offsets (
            video_id TEXT PRIMARY KEY,
            intro_offset REAL NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'none',
            estimated_delta REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Older installs may already have video_offsets without the metadata
        # columns added by the intro-sync feature. Keep those databases usable
        # without dropping the user's permanent calibrations.
        offset_columns = {row[1] for row in db.execute("PRAGMA table_info(video_offsets)").fetchall()}
        for column, definition in (("intro_offset", "REAL NOT NULL DEFAULT 0"),
                                   ("source", "TEXT NOT NULL DEFAULT 'none'"),
                                   ("estimated_delta", "REAL"),
                                   ("updated_at", "TIMESTAMP")):
            if column not in offset_columns:
                db.execute(f"ALTER TABLE video_offsets ADD COLUMN {column} {definition}")
        # Canonical entities retain one row per normalized recording while
        # track_sources preserves every provider-specific playable identity.
        db.execute("""CREATE TABLE IF NOT EXISTS canonical_tracks (
            id TEXT PRIMARY KEY,
            title_norm TEXT NOT NULL,
            artist_norm TEXT NOT NULL,
            duration_sec INTEGER NOT NULL,
            isrc TEXT,
            preferred_source TEXT NOT NULL CHECK (preferred_source IN ('youtube', 'soundcloud')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS track_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_id TEXT NOT NULL REFERENCES canonical_tracks(id) ON DELETE CASCADE,
            source TEXT NOT NULL CHECK (source IN ('youtube', 'soundcloud')),
            source_id TEXT NOT NULL,
            raw_title TEXT NOT NULL,
            raw_artist TEXT NOT NULL,
            duration_sec INTEGER NOT NULL,
            stream_url TEXT,
            UNIQUE(source, source_id)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS merge_review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incoming_source TEXT NOT NULL,
            incoming_source_id TEXT NOT NULL,
            incoming_title TEXT NOT NULL,
            incoming_artist TEXT NOT NULL,
            incoming_duration INTEGER NOT NULL,
            candidate_canonical_id TEXT NOT NULL REFERENCES canonical_tracks(id) ON DELETE CASCADE,
            confidence_score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_track_sources_canonical ON track_sources(canonical_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_track_sources_lookup ON track_sources(source, source_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_merge_review_status ON merge_review_queue(status)")
        db.execute("""CREATE TABLE IF NOT EXISTS favorite_artists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            thumbnail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS playlist_history (
            playlist_id TEXT PRIMARY KEY,
            title TEXT,
            thumbnail TEXT,
            track_count INTEGER,
            last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Existing listens predate multi-source support. Add nullable linkage
        # columns, then populate them from the legacy YouTube identifiers.
        listen_columns = {row[1] for row in db.execute("PRAGMA table_info(listens)").fetchall()}
        for column, definition in (("canonical_id", "TEXT REFERENCES canonical_tracks(id)"),
                                   ("source", "TEXT NOT NULL DEFAULT 'youtube'"),
                                   ("source_id", "TEXT")):
            if column not in listen_columns:
                db.execute(f"ALTER TABLE listens ADD COLUMN {column} {definition}")
        backfill_listens(db)

init_stats_db()

def find_auth_file():
    return next((path for path in AUTH_CANDIDATES if path.is_file()), None)

def artwork(value, size=1000):
    """Return the best thumbnail plus an animated URL when YouTube supplies one."""
    items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
    items = [item for item in items if isinstance(item, dict) and item.get("url")]
    if not items:
        return {"thumbnail": None, "canvas": None}
    def large(url):
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}w={size}&h={size}&resize=fit"
    animated = next((item.get("url") for item in items if item.get("url", "").lower().split("?")[0].endswith((".gif", ".webm", ".mp4"))), None)
    return {"thumbnail": large(items[-1]["url"]), "canvas": animated}

def thumbnail(value, size=1000):
    return artwork(value, size)["thumbnail"]

def make_yt(auth_file=None):
    from ytmusicapi import YTMusic
    auth = auth_file or find_auth_file()
    return YTMusic(str(auth)) if auth else YTMusic()

STARTUP_ERROR = None
yt = None
AUTHENTICATED = find_auth_file() is not None
# (path, mtime_ns, size) of the credential file the live client was built from.
_yt_source = None


def sapisid_from_cookie(cookie_string):
    """Extract the SAPISID value YouTube signs requests with."""
    for part in str(cookie_string or "").split(";"):
        part = part.strip()
        for key in ("__Secure-3PAPISID", "__Secure-1PAPISID", "SAPISID"):
            if part.startswith(key + "="):
                return part.split("=", 1)[1].strip() or None
    return None


def generate_sapisidhash(cookie_string, origin="https://music.youtube.com"):
    """Compute a fresh, origin-bound SAPISIDHASH, mirroring ytmusicapi's
    get_authorization(): sha1(timestamp + ' ' + SAPISID + ' ' + origin).
    Captured hashes expire and bind to the origin they were copied from, so a
    regenerated one is far more likely to be accepted than any pasted value.
    """
    sapisid = sapisid_from_cookie(cookie_string)
    if not sapisid:
        return None
    stamp = str(int(time.time()))
    digest = hashlib.sha1(f"{stamp} {sapisid} {origin}".encode("utf-8")).hexdigest()
    return f"SAPISIDHASH {stamp}_{digest}"


def sanitize_auth_headers(headers):
    """Repair a captured browser.json header set for ytmusicapi.

    Browser extensions sometimes paste an Authorization with three concatenated
    hashes (SAPISIDHASH + SAPISID1PHASH + SAPISID3PHASH); YouTube rejects the
    whole string. Prefer a freshly computed, origin-bound hash from the SAPISID
    cookie; fall back to the first well-formed SAPISIDHASH token. Never touches
    the on-disk file — the sanitized copy is only used in memory.
    """
    if not isinstance(headers, dict):
        return headers
    # ytmusicapi computes the per-request SAPISIDHASH from the Origin/X-Origin
    # header. Captured header dumps omit it, so the client would sign requests
    # with origin "None" and YouTube would treat every call as logged out.
    if not headers.get("Origin") and not headers.get("X-Origin"):
        headers["Origin"] = "https://music.youtube.com"
        headers["X-Origin"] = "https://music.youtube.com"
    fresh = generate_sapisidhash(headers.get("Cookie", ""))
    if fresh:
        headers["Authorization"] = fresh
        return headers
    authorization = headers.get("Authorization") or ""
    if isinstance(authorization, str) and "SAPISIDHASH" in authorization:
        for chunk in authorization.split("SAPISIDHASH"):
            token = chunk.strip().split()
            if token and re.fullmatch(r"\d+_[A-Za-z0-9_-]+", token[0]):
                headers["Authorization"] = f"SAPISIDHASH {token[0]}"
                break
    return headers


def enrich_client_context(client, parsed):
    """Stamp the live client's request context with the user's real browser
    footprint parsed from browser.json, instead of ytmusicapi's generic
    defaults. YouTube's recommendation engine keys off these fields, so
    mismatched hl/gl/timeZone/visitor data makes personalized shelves drift.

    Mutates the client in place: context is merged into every request body by
    ytmusicapi, and base_headers carries the X-Goog-Visitor-Id we inject.
    All parsing is best-effort; a missing field just keeps the default.
    """
    try:
        headers = parsed.get("headers", parsed) if isinstance(parsed, dict) else {}
        if not isinstance(headers, dict):
            return
        cookie = str(headers.get("Cookie") or headers.get("cookie") or "")
        ctx = client.context.setdefault("context", {}).setdefault("client", {})
        # hl from Accept-Language (e.g. "en-US,en;q=0.9" -> "en-US")
        accept_language = str(headers.get("Accept-Language") or headers.get("accept-language") or "")
        if accept_language:
            lang = accept_language.split(",")[0].split(";")[0].strip()
            if lang:
                ctx["hl"] = lang
        # gl from VISITOR_PRIVACY_METADATA (base64-encodes the region, e.g.
        # "CgJHQg==" -> "GB") or SOCS; falls back to the Accept-Language
        # country suffix.
        region = None
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("VISITOR_PRIVACY_METADATA=") or part.startswith("SOCS="):
                encoded = part.split("=", 1)[1].strip()
                try:
                    decoded = urllib.parse.unquote(encoded)
                    import base64
                    decoded = base64.b64decode(decoded + "=="[: (4 - len(decoded) % 4) % 4])
                    match = re.search(rb"[A-Z]{2}", decoded)
                    if match:
                        region = match.group(0).decode("ascii")
                except Exception:
                    region = None
                if region:
                    break
        if not region and "-" in (accept_language or ""):
            country = accept_language.split(",")[0].split("-")[-1].strip()
            if len(country) == 2 and country.isalpha():
                region = country.upper()
        if region:
            ctx["gl"] = region
        # timeZone from PREF=tz=Europe.London (the browser's own timezone)
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("PREF="):
                params = urllib.parse.parse_qs(part.split("=", 1)[1])
                tz = (params.get("tz") or [None])[0]
                if tz:
                    # Google's PREF cookie encodes slashes as dots
                    # (tz=Europe.London); YouTube's context expects IANA form.
                    ctx["timeZone"] = urllib.parse.unquote(tz).replace(".", "/")
                break
        # visitorData from the browser's VISITOR_INFO1_LIVE cookie; also
        # injected as the X-Goog-Visitor-Id request header so every call
        # carries the same visitor identity as the captured browser session.
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("VISITOR_INFO1_LIVE="):
                visitor = part.split("=", 1)[1].strip()
                if visitor:
                    ctx["visitorData"] = visitor
                    try:
                        client.base_headers["X-Goog-Visitor-Id"] = visitor
                    except Exception:
                        pass
                break
    except Exception:
        pass


def build_yt_client(auth):
    """Construct the client from a credential file.

    Two shapes are supported: browser-headers JSON (sanitized in memory so a
    malformed pasted Authorization never breaks auth) and ytmusicapi OAuth
    token JSON, which needs the stored OAuth client credentials to refresh.
    The client's request context is then stamped with the user's real browser
    footprint so YouTube's personalized shelves align with the listening
    profile that captured the credentials.
    """
    from ytmusicapi import YTMusic
    try:
        parsed = json.loads(auth.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return make_yt(auth)
    if isinstance(parsed, dict) and "refresh_token" in parsed:
        credentials = oauth_credentials_from_store()
        if credentials is None:
            raise RuntimeError("oauth.json found but no stored OAuth client: re-run the Connect with Google flow")
        client = YTMusic(str(auth), oauth_credentials=credentials)
        enrich_client_context(client, parsed)
        return client
    if isinstance(parsed, dict) and any(key in parsed for key in ("User-Agent", "Cookie", "Authorization")):
        client = YTMusic(sanitize_auth_headers(parsed))
        enrich_client_context(client, parsed)
        return client
    return make_yt(auth)


def get_yt():
    """Return the singleton authenticated client, rebuilding it whenever the
    credential file appears, disappears, or changes on disk.

    This is the single entry point for every authenticated call. It never
    creates or deletes browser.json — only /api/auth/logout may remove
    credentials — so normal request flows can never accidentally wipe the
    session file or keep serving a stale in-memory client after a re-auth.
    """
    global yt, AUTHENTICATED, STARTUP_ERROR, _yt_source
    auth = find_auth_file()
    if auth is None:
        if yt is not None:
            yt, AUTHENTICATED, STARTUP_ERROR = None, False, None
        return None
    try:
        stat = auth.stat()
        # The time bucket forces a periodic rebuild (and a fresh SAPISIDHASH)
        # roughly every 6 hours, so the in-memory signature never goes stale.
        source = (str(auth), stat.st_mtime_ns, stat.st_size, int(time.time()) // 21600)
    except OSError:
        source = None
    if yt is None or source != _yt_source:
        try:
            yt = build_yt_client(auth)
            AUTHENTICATED, STARTUP_ERROR = True, None
            _yt_source = source
        except Exception as exc:
            yt, AUTHENTICATED, STARTUP_ERROR = None, False, str(exc)
            return None
    return yt

def auth_headers():
    """Extract browser session headers from common ytmusicapi browser.json shapes."""
    path = find_auth_file()
    if not path:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict):
        headers = data.get("headers", data)
        if isinstance(headers, dict):
            return {str(key).replace("_", "-"): str(value) for key, value in headers.items()
                    if key.lower().replace("_", "-") in ("cookie", "user-agent") and value}
    return {}

def clean_track_meta(title, artist):
    """Normalize music metadata before catalog/lyrics lookups."""
    clean_title = clean(title)
    clean_title = re.sub(r"\s*[\(\[](?:feat\.|ft\.|with).*?[\)\]]", "", clean_title, flags=re.I)
    clean_title = re.sub(r"\s*[\(\[](?:(?:official\s*(?:music\s*)?(?:video|audio))|visualizer|lyrics?|hd|4k|remastered).*?[\)\]]", "", clean_title, flags=re.I)
    clean_title = re.sub(r"\s+-\s+.*$", "", clean_title).strip()
    clean_artist = re.sub(r"\s*-\s*Topic(?=\s*(?:,|$))", "", clean(artist), flags=re.I)
    clean_artist = re.sub(r",.*$", "", clean_artist).strip()
    return clean_title, clean_artist


def parse_lrc(text):
    lines = []
    for raw in (text or "").splitlines():
        matches = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", raw)
        lyric = re.sub(r"(?:\[\d+:\d+(?:\.\d+)?\])+", "", raw).strip()
        for minutes, seconds in matches:
            if lyric:
                lines.append({"time": int(minutes) * 60 + float(seconds), "text": clean(lyric)})
    return sorted(lines, key=lambda line: line["time"])

def api_error(exc, status=502):
    return jsonify({"error": str(exc), "hint": "Add valid ytmusicapi browser headers and try again."}), status

def search_item(item, forced_kind=None):
    if not isinstance(item, dict):
        return None
    kind = forced_kind or item.get("resultType", "song")
    # ytmusicapi uses singular resultType values, while a few versions return
    # a filter-shaped value. Keep the frontend contract stable regardless of
    # which response shape the installed client emits.
    kind = {"songs": "song", "artists": "artist", "albums": "album", "playlists": "playlist"}.get(kind, kind)
    artists = item.get("artists") or item.get("artist") or item.get("author") or []
    artist_name = _first_artist(artists)
    artist_id = next((clean(a.get("id")) for a in artists if isinstance(a, dict) and a.get("id")), None) if isinstance(artists, list) else None
    album = item.get("album")
    album_name = clean(_field_text(album))
    video_id = clean(item.get("videoId") or item.get("id"))
    browse_id = clean(item.get("browseId") or item.get("playlistId"))
    if kind == "artist" and not browse_id:
        # Artists surface their channel as browseId in some API versions; use it
        # so artist cards stay navigable. Other kinds must NOT inherit it or
        # video/shelf results would collide with the artist card's id.
        browse_id = artist_id
    album_id = clean(album.get("id")) if isinstance(album, dict) else None
    normalized = normalize_track(item) if kind == "song" else None
    if kind == "song" and not normalized:
        return None
    value = {"id": normalized["videoId"] if normalized else (video_id if kind == "song" else browse_id),
             "type": kind, "title": normalized["title"] if normalized else (clean(_field_text(item.get("title"))) or clean(_field_text(item.get("name"))) or (artist_name if kind == "artist" else "")),
             "artist": normalized["artist"] if normalized else artist_name, "artistId": artist_id,
             "album": album_name, "albumId": album_id, "thumbnail": normalized["thumbnail"] if normalized else _thumbnail_url(item.get("thumbnails") or item.get("thumbnail"))}
    if kind == "song":
        value["videoId"] = normalized["videoId"]
        value["duration"] = normalized["duration"]
    return value

@app.get("/api/search")
@rate_limit("search", 8, 10)
def search():
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    query = clean(request.args.get("q"))[:120]
    allowed = {"songs": "songs", "albums": "albums", "artists": "artists", "playlists": "playlists"}
    filter_name = allowed.get(clean(request.args.get("filter")).lower())
    if not query:
        return jsonify({"query": "", "results": []})
    try:
        if filter_name:
            raw_results = client.search(query, filter=filter_name)
            items = [item for item in (search_item(raw, filter_name[:-1] if filter_name.endswith("s") else filter_name)
                                      for raw in raw_results) if item]
        else:
            # One broad search is not enough: YouTube Music tends to fill it
            # with songs and silently omit artists/albums. Fetch each catalog
            # type explicitly, then concatenate in the UI's intentional order.
            groups = []
            failures = []
            for kind, api_filter in (("song", "songs"), ("artist", "artists"),
                                     ("album", "albums"), ("playlist", "playlists")):
                try:
                    try:
                        raw_results = client.search(query, filter=api_filter, limit=20)
                    except TypeError:
                        raw_results = client.search(query, filter=api_filter)
                    groups.extend(search_item(item, kind) for item in (raw_results or [])
                                  if isinstance(item, dict))
                except Exception as category_error:
                    # Keep the useful categories if one filter is unsupported
                    # by a particular ytmusicapi/YouTube response.
                    failures.append(f"{api_filter}: {category_error}")
            items = [item for item in groups if item]
            if not items and failures:
                raise RuntimeError("No searchable result categories were available")
        # Artist results without any channel ID are un-navigable: drop them so
        # the shelf never renders a card that cannot open its artist page.
        items = [item for item in items if item and not (item["type"] == "artist" and not item["id"])
                and not (item["type"] == "song" and normalize_track(item) is None)]
        return jsonify({"query": query, "results": items,
                        "songs": [item for item in items if item["type"] == "song"],
                        "artists": [item for item in items if item["type"] == "artist"],
                        "albums": [item for item in items if item["type"] == "album"],
                        "playlists": [item for item in items if item["type"] == "playlist"]})
    except Exception as exc:
        traceback.print_exc()
        print(f"Search failed for query={query!r}: {exc}", flush=True)
        return jsonify({"error": str(exc), "results": []}), 500


def require_yt():
    client = get_yt()
    if client is None:
        raise RuntimeError("An authenticated YouTube Music session is required")
    return client

@app.post("/api/playlist/create")
def create_playlist():
    body = request.get_json(silent=True) or {}
    try:
        playlist_id = require_yt().create_playlist(clean(body.get("title")), clean(body.get("description")))
        return jsonify({"ok": True, "id": playlist_id}), 201
    except Exception as exc:
        return api_error(exc, 400)

@app.post("/api/playlist/delete")
def delete_playlist():
    playlist_id = clean((request.get_json(silent=True) or {}).get("playlist_id"))
    if not valid_playlist_id(playlist_id):
        return jsonify({"error": "Invalid playlist id", "ok": False}), 400
    try:
        require_yt().delete_playlist(playlist_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return api_error(exc, 400)

@app.post("/api/playlist/edit")
def edit_playlist():
    body = request.get_json(silent=True) or {}
    playlist_id = clean(body.get("playlist_id"))
    if not valid_playlist_id(playlist_id):
        return jsonify({"error": "Invalid playlist id", "ok": False}), 400
    try:
        require_yt().edit_playlist(playlist_id, title=clean(body.get("title")), description=clean(body.get("description")))
        return jsonify({"ok": True})
    except Exception as exc:
        return api_error(exc, 400)

@app.post("/api/playlist/add-track")
def add_track():
    body = request.get_json(silent=True) or {}
    playlist_id, video_id = clean(body.get("playlist_id")), clean(body.get("video_id"))
    if not valid_playlist_id(playlist_id) or not valid_video_id(video_id):
        return jsonify({"error": "Invalid playlist id or video id", "ok": False}), 400
    try:
        require_yt().add_playlist_items(playlist_id, [video_id])
        return jsonify({"ok": True})
    except Exception as exc:
        return api_error(exc, 400)

@app.post("/api/playlist/remove-track")
def remove_track():
    body = request.get_json(silent=True) or {}
    playlist_id, video_id = clean(body.get("playlist_id")), clean(body.get("video_id"))
    if not valid_playlist_id(playlist_id) or not valid_video_id(video_id):
        return jsonify({"error": "Invalid playlist id or video id", "ok": False}), 400
    try:
        require_yt().remove_playlist_items(playlist_id, [video_id])
        return jsonify({"ok": True})
    except Exception as exc:
        return api_error(exc, 400)


# Membership scans walk every owned playlist, so results are cached per video
# id for the session; the picker sheet re-opens instantly for a re-add.
PLAYLIST_MEMBERSHIP_CACHE = {}
PLAYLIST_MEMBERSHIP_TTL = 10 * 60  # seconds

@app.get("/api/playlist/membership")
def playlist_membership():
    """Return which owned playlists already contain the given video id.

    Checking playlists serially would stall the add-to-playlist sheet, so each
    playlist is scanned in its own client thread and the result is cached.
    LM (Liked Music) is excluded: this app does not treat it as an editable
    playlist. Failures on individual playlists degrade to "not present" rather
    than failing the whole sheet.
    """
    video_id = clean(request.args.get("video_id"))
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id", "ok": False}), 400
    cached = PLAYLIST_MEMBERSHIP_CACHE.get(video_id)
    if cached and time.time() - cached[0] < PLAYLIST_MEMBERSHIP_TTL:
        return jsonify({"membership": cached[1]})
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        ids = [clean(p.get("playlistId")) for p in client.get_library_playlists(limit=None)]
        ids = [pid for pid in ids if valid_playlist_id(pid) and pid != "LM"]

        def _has_track(pid):
            # ytmusicapi sessions are not thread-safe: one client per worker.
            try:
                worker = build_yt_client(find_auth_file())
                tracks = worker.get_playlist(pid, limit=None).get("tracks", [])
                return pid, any(t.get("videoId") == video_id for t in tracks)
            except Exception:
                return pid, False

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(ids)))) as pool:
            membership = dict(pool.map(_has_track, ids))
    except Exception as exc:
        return api_error(exc)
    PLAYLIST_MEMBERSHIP_CACHE[video_id] = (time.time(), membership)
    return jsonify({"membership": membership})

def clean(value):
    """Normalize metadata from YouTube's inconsistent text fields."""
    return " ".join(str(value or "").replace("\\n", " ").replace("\\r", " ").replace("\\t", " ").split()).strip()

def _field_text(value):
    """Extract display text from the shapes returned by YT Music and yt-dlp."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        if value.get("text") is not None:
            return _field_text(value.get("text"))
        runs = value.get("runs")
        if isinstance(runs, list):
            return "".join(_field_text(run) for run in runs if isinstance(run, dict) or isinstance(run, str))
        for key in ("name", "title", "label", "simpleText"):
            if value.get(key) is not None:
                return _field_text(value[key])
    return ""


def _first_artist(value):
    if isinstance(value, list):
        for item in value:
            text = _first_artist(item)
            if text:
                return text
        return ""
    return _field_text(value)


def _thumbnail_url(value):
    """Return the highest-resolution URL from list, object, or string shapes."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if value.get("url"):
            return str(value["url"]).strip()
        for key in ("thumbnails", "thumbnail", "sources"):
            result = _thumbnail_url(value.get(key))
            if result:
                return result
        return ""
    if isinstance(value, list):
        for item in reversed(value):
            result = _thumbnail_url(item)
            if result:
                return result
    return ""


def normalize_track(item):
    """Normalize a playable track across YT Music and yt-dlp payload shapes.

    This is deliberately strict: a malformed shelf row is dropped at the
    boundary instead of leaking "Unknown title" / "Unknown artist" cards into
    every frontend view. Callers must filter the returned ``None`` values.
    """
    if not isinstance(item, dict):
        return None
    title = (_field_text(item.get("title")) or _field_text(item.get("name")) or
             _field_text(item.get("headline")))
    artists_field = item.get("artists") or item.get("artist") or item.get("author")
    artist = _first_artist(artists_field)
    artwork_value = item.get("thumbnails") or item.get("thumbnail") or item.get("artwork")
    artwork_url = _thumbnail_url(artwork_value)
    track_id = item.get("videoId") or item.get("id") or item.get("track_id")
    title = clean(title)
    artist = clean(artist)
    track_id = clean(track_id)
    placeholder_titles = {"unknown", "unknown title", "unknown audio", "untitled", ""}
    if not title or not track_id or title.lower() in placeholder_titles or not artwork_url:
        return None
    duration = item.get("duration") or item.get("duration_seconds") or item.get("length") or item.get("lengthSeconds") or 0
    return {
        "id": str(track_id),
        "videoId": str(track_id),
        "title": title,
        "artist": artist or "Various Artists",
        "artwork": artwork_url,
        "thumbnail": artwork_url,
        "duration": duration,
    }


def track_data(track):
    normalized = normalize_track(track)
    if not normalized:
        return None
    artists_field = track.get("artists") or track.get("artist") or track.get("author")
    artist_list = artists_field if isinstance(artists_field, list) else [artists_field]
    artist_id = next((clean(a.get("id")) for a in artist_list if isinstance(a, dict) and a.get("id")), None)
    album = track.get("album")
    album_name = clean(_field_text(album))
    album_id = clean(album.get("id")) if isinstance(album, dict) else None
    art = artwork(track.get("thumbnails") or track.get("thumbnail") or track.get("artwork"))
    return {
        **normalized,
        "artistId": artist_id,
        "album": album_name,
        "albumId": album_id,
        "canvas": art["canvas"] if art else None,
    }

def session_state():
    """Probe the live session's entitlement with one lightweight liked-song call.

    When browser.json credentials lapse, YouTube serves the logged-out liked
    page ("Looking for what you've liked?") and ytmusicapi raises a parse
    error — the earliest reliable signal that the session needs re-auth.
    """
    client = get_yt()
    if client is None:
        return "unauthenticated"
    try:
        client.get_liked_songs(limit=1)
        return "ok"
    except Exception:
        return "expired"


def is_auth_failure(exc):
    """Detect ytmusicapi/YouTube auth-lapse signals from an exception.

    Distinguishes "credentials expired" (serve cached library data, show the
    re-auth banner) from genuine API/network errors (report them normally).
    """
    if exc is None:
        return False
    if exc.__class__.__name__.lower().startswith("ytmusic"):
        # ytmusicapi raises dedicated classes for missing/invalid auth headers.
        if "auth" in exc.__class__.__name__.lower():
            return True
    message = str(exc or "").lower()
    markers = (
        "you must be authenticated", "authentication", "auth headers",
        "sign in", "sign-in", "log in", "logged out", "logged-in",
        "looking for what you've liked", "messageRenderer", "permission",
        "requires_auth", "status_code: 401", "status_code: 403",
    )
    return any(marker in message for marker in markers)


def oauth_credentials_from_store():
    """Load OAuth client credentials (id/secret) saved by the device flow."""
    try:
        data = json.loads(OAUTH_CLIENT_PATH.read_text(encoding="utf-8"))
        client_id, client_secret = data.get("client_id"), data.get("client_secret")
        if client_id and client_secret:
            from ytmusicapi.auth.oauth.credentials import OAuthCredentials
            return OAuthCredentials(client_id, client_secret)
    except (OSError, json.JSONDecodeError, ImportError):
        pass
    return None


OAUTH_PENDING = {"code": None, "credentials": None}


@app.post("/api/auth/oauth/init")
def oauth_init():
    """Start the Google device flow: return the verification URL  + user code."""
    global yt, AUTHENTICATED, STARTUP_ERROR, _yt_source
    body = request.get_json(silent=True) or {}
    client_id = clean(body.get("client_id"))
    client_secret = clean(body.get("client_secret"))
    if not client_id or not client_secret:
        return jsonify({"error": "Both client_id and client_secret are required (Google Cloud Console, YouTube Data API v3)."}), 400
    try:
        from ytmusicapi.auth.oauth.credentials import OAuthCredentials
        credentials = OAuthCredentials(client_id, client_secret)
        code = credentials.get_code()
    except Exception as exc:
        message = str(exc)
        if "invalid_client" in message or "BadOAuthClient" in type(exc).__name__:
            return jsonify({"error": "Google rejected this client id/secret. Check the OAuth client type ('TVs and Limited Input devices') and that the YouTube Data API v3 is enabled."}), 400
        return api_error(exc, 502)
    OAUTH_PENDING["code"] = code
    OAUTH_PENDING["credentials"] = credentials
    return jsonify({"verification_url": code.get("verification_url"), "user_code": code.get("user_code"),
                    "expires_in": code.get("expires_in"), "interval": code.get("interval", 5)})


@app.post("/api/auth/oauth/complete")
def oauth_complete():
    """Exchange the approved device code for a token and activate the session.

    oauth.json lives OUTSIDE the repo in DATA_DIR and stores a refreshing
    token, so the session survives refreshes without re-pasting cookies.
    """
    global yt, AUTHENTICATED, STARTUP_ERROR, _yt_source
    if not OAUTH_PENDING.get("code") or not OAUTH_PENDING.get("credentials"):
        return jsonify({"error": "No device flow in progress — click Start first."}), 400
    code, credentials = OAUTH_PENDING["code"], OAUTH_PENDING["credentials"]
    try:
        raw = credentials.token_from_code(code["device_code"])
    except Exception as exc:
        message = str(exc)
        if "authorization_pending" in message or "expired_token" in message or "slow_down" in message:
            return jsonify({"error": "Google has not approved the code yet (or it expired) — approve at the link, then try again."}), 400
        return api_error(exc, 502)
    refresh_expires = raw.get("refresh_token_expires_in", raw.get("expires_in", 86400))
    try:
        from ytmusicapi.auth.oauth.token import RefreshingToken as _RT
        refreshing = _RT(credentials=credentials, access_token=raw["access_token"], refresh_token=raw["refresh_token"],
                         scope=raw.get("scope", ""), token_type=raw.get("token_type", "Bearer"),
                         expires_in=refresh_expires)
        refreshing.update(raw)
        refreshing.local_cache = DATA_DIR / "oauth.json"
        refreshing.store_token()
        # Persist the client id/secret alongside so future restarts can refresh.
        OAUTH_CLIENT_PATH.write_text(json.dumps({"client_id": credentials.client_id, "client_secret": credentials.client_secret}), encoding="utf-8")
        yt = build_yt_client(DATA_DIR / "oauth.json")
        _yt_source = None
        AUTHENTICATED, STARTUP_ERROR = True, None
        OAUTH_PENDING["code"] = None
        OAUTH_PENDING["credentials"] = None
        return jsonify({"ok": True, "authenticated": True})
    except Exception as exc:
        return api_error(exc, 400)


def load_library_cache(key):
    """Return the last successful payload for a library endpoint, or None."""
    try:
        data = json.loads(LIBRARY_CACHE_PATH.read_text(encoding="utf-8"))
        return data.get(key)
    except (OSError, json.JSONDecodeError, AttributeError):
        return None

def save_library_cache(key, payload):
    """Persist a successful library payload so a lapsed session degrades gracefully."""
    try:
        LIBRARY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        try:
            data = json.loads(LIBRARY_CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        data[key] = payload
        LIBRARY_CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


@app.get("/api/palette/<video_id>")
@rate_limit("palette", 60, 10)
def get_palette(video_id):
    video_id = clean(video_id)
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400
    with db_connection() as db:
        row = db.execute("SELECT palette_json FROM listens WHERE video_id = ? AND palette_json IS NOT NULL ORDER BY id DESC LIMIT 1", (video_id,)).fetchone()
    if not row:
        return jsonify({"palette": None})
    try:
        palette = json.loads(row["palette_json"])
    except (TypeError, json.JSONDecodeError):
        palette = None
    return jsonify({"palette": palette})


@app.post("/api/palette/<video_id>")
@rate_limit("palette", 30, 10)
def save_palette(video_id):
    video_id = clean(video_id)
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "Palette must be an object"}), 400
    palette = {key: body.get(key) for key in ("accent", "ambient", "shadow", "neutral") if key in body}
    if not palette.get("accent") or not palette.get("ambient"):
        return jsonify({"error": "Palette needs accent and ambient colors"}), 400
    with db_connection() as db:
        row = db.execute("SELECT id FROM listens WHERE video_id = ? ORDER BY id DESC LIMIT 1", (video_id,)).fetchone()
        if row:
            db.execute("UPDATE listens SET palette_json = ? WHERE id = ?", (json.dumps(palette), row["id"]))
        else:
            db.execute("""INSERT INTO listens
                (video_id, title, artist, album, thumbnail_url, played_at_timestamp, listen_duration_seconds, palette_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (video_id, "Unknown title", "Unknown artist", "", None,
                                                        datetime.now(timezone.utc).isoformat(), 0, json.dumps(palette)))
    return jsonify({"ok": True, "video_id": video_id, "palette": palette}), 201


def parse_duration(value):
    """Convert '3:45', '245', or 245 into seconds; None when unparseable."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if ":" in text:
            seconds = 0.0
            for part in text.split(":"):
                seconds = seconds * 60 + float(part)
            return seconds
        return float(text)
    except ValueError:
        return None


def estimate_timestamps(text, duration=None):
    """Turn plain lyrics into estimated per-line timestamps proportional to length.

    This is the last-resort syncing layer: the frontend always gets clickable,
    time-addressable lines so Theatre Mode never degrades to a dead text block.
    """
    lines = [clean(line) for line in (text or "").splitlines() if clean(line)]
    if not lines:
        return []
    total = parse_duration(duration) or 180.0
    weights = [max(1.0, float(len(line))) for line in lines]
    scale = total / sum(weights)
    cursor, result = 0.0, []
    for line, weight in zip(lines, weights):
        result.append({"time": round(cursor, 2), "text": line})
        cursor += weight * scale
    return result


@app.get("/mobile")
def mobile_remote():
    """Serve the installable iPhone remote from the same Flask origin."""
    return send_from_directory(str(Path(__file__).parent / "static"), "mobile.html")


@app.get("/mobile-manifest.webmanifest")
def mobile_manifest():
    return send_from_directory(str(Path(__file__).parent / "static"), "mobile-manifest.webmanifest",
                               mimetype="application/manifest+json")


@app.get("/mobile-sw.js")
def mobile_service_worker():
    response = send_from_directory(str(Path(__file__).parent / "static"), "mobile-sw.js",
                                   mimetype="application/javascript")
    # Keep the remote's service worker from claiming the desktop frontend at /
    # on the same backend origin.
    response.headers["Service-Worker-Allowed"] = "/mobile"
    return response


@app.get("/mobile-icon.svg")
def mobile_icon_svg():
    return send_from_directory(str(Path(__file__).parent / "static"), "mobile-icon.svg",
                               mimetype="image/svg+xml")


@app.get("/mobile-icon.png")
def mobile_icon_png():
    return send_from_directory(str(ROOT / "public" / "icons"), "icon-192.png",
                               mimetype="image/png")


@app.get("/api/remote/state")
def remote_state():
    """Return the desktop player's latest published state and queued commands."""
    with REMOTE_LOCK:
        prune_remote_commands()
        return jsonify({**REMOTE_STATE, "pending_commands": list(REMOTE_COMMANDS)})


@app.post("/api/remote/state")
def publish_remote_state():
    """Publish source-of-truth playback state from the desktop frontend."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Remote state must be an object"}), 400
    with REMOTE_LOCK:
        for key in ("is_playing", "shuffle"):
            if key in data and isinstance(data[key], bool):
                REMOTE_STATE[key] = data[key]
        if "repeat" in data and data["repeat"] in ("off", "all", "one"):
            REMOTE_STATE["repeat"] = data["repeat"]
        for key in ("current_time", "duration", "volume"):
            if key in data:
                try:
                    value = float(data[key])
                    if not math.isfinite(value):
                        continue
                    if key == "volume": value = max(0.0, min(1.0, value))
                    if key != "volume": value = max(0.0, value)
                    REMOTE_STATE[key] = value
                except (TypeError, ValueError):
                    pass
        if "current_track" in data:
            track = data["current_track"]
            REMOTE_STATE["current_track"] = track if isinstance(track, dict) else None
        if isinstance(data.get("queue"), list):
            REMOTE_STATE["queue"] = [item for item in data["queue"][:100] if isinstance(item, dict)]
        if isinstance(data.get("lyrics"), list):
            REMOTE_STATE["lyrics"] = [item for item in data["lyrics"][:300] if isinstance(item, dict)]
        REMOTE_STATE["updated_at"] = time.time()
        return jsonify({"success": True, **REMOTE_STATE})


@app.post("/api/remote/command")
def remote_command():
    """Queue a validated playback command for the desktop player to execute."""
    global REMOTE_COMMAND_ID
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Remote command must be an object"}), 400
    action, payload = data.get("action"), data.get("payload")
    if not isinstance(action, str) or action not in REMOTE_ACTIONS:
        return jsonify({"error": "Unsupported remote command"}), 400
    if action == "seek":
        try:
            payload = float(payload)
            if not math.isfinite(payload):
                raise ValueError
            payload = max(0.0, payload)
            if REMOTE_STATE["duration"] > 0:
                payload = min(payload, REMOTE_STATE["duration"])
        except (TypeError, ValueError):
            return jsonify({"error": "Seek position must be a finite number"}), 400
    elif action == "set_volume":
        try:
            payload = float(payload)
            if not math.isfinite(payload):
                raise ValueError
            payload = max(0.0, min(1.0, payload))
        except (TypeError, ValueError):
            return jsonify({"error": "Volume must be a finite number between 0 and 1"}), 400
    elif action == "play_track":
        if not isinstance(payload, dict):
            return jsonify({"error": "Track payload must be an object"}), 400
        payload = {key: payload.get(key) for key in
                   ("id", "videoId", "canonicalId", "title", "artist", "album", "thumbnail", "duration")
                   if payload.get(key) is not None}
        video_id = payload.get("videoId")
        canonical_id = payload.get("canonicalId")
        track_id = video_id or canonical_id or payload.get("id")
        if video_id and not valid_video_id(video_id):
            return jsonify({"error": "Track videoId is invalid"}), 400
        if canonical_id and not valid_canonical_id(canonical_id):
            return jsonify({"error": "Track canonicalId is invalid"}), 400
        if not video_id and not (valid_video_id(track_id) or valid_canonical_id(track_id)):
            return jsonify({"error": "Track is missing a valid id"}), 400
    with REMOTE_LOCK:
        prune_remote_commands()
        REMOTE_COMMAND_ID += 1
        command = {"id": REMOTE_COMMAND_ID, "action": action, "payload": payload,
                   "created_at": time.time()}
        REMOTE_COMMANDS.append(command)
        del REMOTE_COMMANDS[:-50]
        # Optimistic values make the phone feel immediate; the desktop's next
        # state publication remains authoritative and corrects any divergence.
        if action == "toggle_play": REMOTE_STATE["is_playing"] = not REMOTE_STATE["is_playing"]
        elif action == "seek": REMOTE_STATE["current_time"] = payload
        elif action == "set_volume": REMOTE_STATE["volume"] = payload
        elif action == "play_track":
            REMOTE_STATE["current_track"] = payload
            REMOTE_STATE["current_time"] = 0.0
            REMOTE_STATE["is_playing"] = True
        REMOTE_STATE["updated_at"] = time.time()
        return jsonify({"success": True, "command_id": REMOTE_COMMAND_ID,
                        "state": {**REMOTE_STATE, "pending_commands": list(REMOTE_COMMANDS)}}), 202


@app.post("/api/remote/commands/ack")
def acknowledge_remote_commands():
    """Remove commands already executed by the desktop player."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Acknowledgement must be an object"}), 400
    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be an array"}), 400
    try:
        known = {int(value) for value in ids}
    except (TypeError, ValueError):
        return jsonify({"error": "ids must contain integers"}), 400
    with REMOTE_LOCK:
        prune_remote_commands()
        REMOTE_COMMANDS[:] = [command for command in REMOTE_COMMANDS if command["id"] not in known]
        return jsonify({"success": True, "remaining": len(REMOTE_COMMANDS)})


@app.get("/api/health")
def health():
    session = session_state()
    # A lapsed session is reported honestly: status flips to "expired" and
    # authenticated drops to false so consumers never trust a dead session.
    return jsonify({"status": "expired" if session == "expired" else "ok",
                    "port": 5178, "backend": "ytm-player",
                    "ytmusic": get_yt() is not None,
                    "authenticated": AUTHENTICATED and session != "expired",
                    "session": session})


@app.post("/api/auth/logout")
def auth_logout():
    """Forget the stored credentials and drop the live client.

    This is the ONLY place browser.json may be removed: normal error flows and
    request handling never touch the credential file.
    """
    global yt, AUTHENTICATED, STARTUP_ERROR, _yt_source
    for path in (AUTH_PATH, DATA_DIR / "oauth.json"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    yt = None
    AUTHENTICATED = False
    STARTUP_ERROR = None
    _yt_source = None
    return jsonify({"ok": True, "authenticated": False})


@app.get("/api/settings")
def get_settings():
    return jsonify({
        "quality": SETTINGS.get("quality", "high"),
        "cache_limit_bytes": SETTINGS.get("cache_limit_bytes", CACHE_LIMIT_BYTES),
        "cache": cache_info(),
        "authenticated": AUTHENTICATED,
    })


@app.post("/api/settings")
def update_settings():
    global SETTINGS
    body = request.get_json(silent=True) or {}
    data = {}
    quality = body.get("quality")
    if quality in QUALITY_FORMATS:
        data["quality"] = quality
    limit = body.get("cache_limit_bytes")
    if limit is not None:
        try:
            limit = int(limit)
            if 16 * 1024 * 1024 <= limit <= 64 * 1024 ** 3:
                data["cache_limit_bytes"] = limit
        except (TypeError, ValueError):
            pass
    if not data:
        return jsonify({"error": "No valid settings provided", "ok": False}), 400
    SETTINGS = save_settings(data)
    evict_cache()
    return jsonify({"ok": True,
                    "quality": SETTINGS["quality"],
                    "cache_limit_bytes": SETTINGS["cache_limit_bytes"],
                    "cache": cache_info()})


@app.post("/api/settings/cache/clear")
def clear_cache():
    """Delete every cached audio file."""
    cleared = 0
    if CACHE_DIR.is_dir():
        for path in CACHE_DIR.iterdir():
            if path.is_file():
                try:
                    path.unlink()
                    cleared += 1
                except OSError:
                    pass
    return jsonify({"ok": True, "cleared": cleared, "cache": cache_info()})


def parse_headers_text(raw):
    """Parse pasted raw request headers ("Key: Value" lines, optionally from a
    copied cURL command) into a plain headers dict. ytmusicapi 1.12 moved setup()
    to module scope and no longer exposes YTMusic.setup(), so raw text is parsed
    here instead of delegating to the old helper.
    """
    headers = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("curl ") or "-h " in lowered:
            # cURL output: pull every -H 'Key: Value' token and skip the rest.
            for match in re.finditer(r"-H\s+['\"]([^'\"]+)['\"]", line):
                header = match.group(1)
                if ":" in header:
                    key, _, value = header.partition(":")
                    headers[key.strip()] = value.strip()
            continue
        if lowered.startswith(("-a ", "-x ")):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().strip("'\"")
        if key:
            headers[key] = value.strip().strip("'\"")
    return headers


@app.post("/api/auth/setup")
def auth_setup():
    """Validate and atomically persist pasted ytmusicapi credentials.

    Accepts either browser.json JSON or raw copied request headers (plain
    "Key: Value" lines or cURL output). The payload is parsed, sanitized, and
    proven with a live authenticated call BEFORE it replaces the stored
    credential, then the running singleton client is re-initialized from the
    newly saved file so no backend restart is needed.
    """
    global yt, AUTHENTICATED, STARTUP_ERROR, _yt_source
    body = request.get_json(silent=True) or {}
    raw = body.get("auth") or body.get("headers") or body.get("config")
    if not isinstance(raw, str) or not raw.strip():
        return api_error(ValueError("Paste the contents of browser.json or raw request headers."), 400)

    parsed = None
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Authentication JSON must be an object.")
    except json.JSONDecodeError:
        parsed = parse_headers_text(raw)
        if not parsed:
            return api_error(ValueError("Could not parse authentication data: paste browser.json JSON or raw request headers (Key: Value lines)."), 400)
        if not any(key.lower() in ("cookie", "authorization") for key in parsed):
            return api_error(ValueError("Parsed headers are missing a Cookie or Authorization header."), 400)

    temp_name = None
    try:
        # Prove the credential works before touching the stored file: build a
        # candidate from the sanitized payload and hit the account directly.
        # get_library_playlists() returns [] silently for a lapsed session, so
        # probe get_liked_songs() instead — it raises exactly when the session
        # is dead (same check /api/health uses), preventing false "success".
        from ytmusicapi import YTMusic
        candidate = YTMusic(sanitize_auth_headers(dict(parsed)))
        liked = candidate.get_liked_songs(limit=1)
        if not isinstance(liked, dict) or "tracks" not in liked:
            raise ValueError("Could not confirm your session: the account returned no liked-songs data.")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=DATA_DIR, encoding="utf-8") as temp:
            json.dump(parsed, temp, indent=2)
            temp_name = temp.name
        os.replace(temp_name, AUTH_PATH)
        yt = build_yt_client(AUTH_PATH)
        _yt_source = None  # force get_yt() to re-derive from the replaced file
        AUTHENTICATED, STARTUP_ERROR = True, None
        return jsonify({"ok": True, "authenticated": True})
    except Exception as exc:
        if temp_name:
            try: os.unlink(temp_name)
            except OSError: pass
        return api_error(exc, 400)

@app.get("/api/lyrics")
@rate_limit("lyrics", 12, 10)
def lyrics():
    title, artist = clean_track_meta(request.args.get("title"), request.args.get("artist"))
    title, artist = title[:200], artist[:200]
    track_id = clean(request.args.get("track_id"))
    duration = request.args.get("duration") or ""
    if track_id and not valid_video_id(track_id):
        track_id = None
    plain = ""
    try:
        # 1. LRCLIB is the preferred source for time-synced lyrics: query artist,
        #    title, and duration so the best matching record wins. LRCLIB requires
        #    duration in SECONDS — the frontend sends "m:ss", so convert first.
        seconds = parse_duration(duration)
        lrclib_params = {"track_name": title, "artist_name": artist}
        if seconds is not None:
            lrclib_params["duration"] = seconds
        params = urllib.parse.urlencode(lrclib_params)
        try:
            with urllib.request.urlopen(f"https://lrclib.net/api/get?{params}", timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            parsed = parse_lrc(data.get("syncedLyrics", ""))
            if parsed:
                return jsonify({"synced": True, "lines": parsed})
            plain = str(data.get("plainLyrics") or "").strip()
        except Exception:
            pass
        # 2. Fall back to YouTube Music's native lyrics when LRCLIB has no record.
        client = get_yt()
        if client is not None and track_id:
            try:
                watch = client.get_watch_playlist(videoId=track_id, limit=1)
                lyrics_id = watch.get("lyrics", {}).get("browseId") if isinstance(watch.get("lyrics"), dict) else watch.get("lyrics")
                if lyrics_id and hasattr(client, "get_lyrics"):
                    result = client.get_lyrics(lyrics_id) or {}
                    plain = plain or str(result.get("lyrics") or "").strip()
                    parsed = parse_lrc(result.get("lyrics", ""))
                    if parsed:
                        return jsonify({"synced": True, "lines": parsed})
            except Exception:
                pass
        # 3. Never degrade to a dead text block: synthesize proportional timestamps
        #    from whatever plain lyrics we found so the frontend lines stay clickable.
        if plain:
            lines = estimate_timestamps(plain, duration)
            if lines:
                return jsonify({"synced": True, "estimated": True, "lines": lines, "text": plain})
        return jsonify({"synced": False, "text": plain, "lines": []})
    except Exception:
        if plain:
            lines = estimate_timestamps(plain, duration)
            if lines:
                return jsonify({"synced": True, "estimated": True, "lines": lines, "text": plain})
        return jsonify({"synced": False, "text": plain, "lines": []})


@app.get("/api/karaoke-lyrics")
@rate_limit("karaoke-lyrics", 8, 10)
def karaoke_lyrics():
    """Return syllable-level lyrics without local audio/ML processing.

    NetEase YRC is preferred for true word timing. If it is unavailable, the
    ordinary timed-line sources are expanded by the small cadence heuristic.
    The response remains compatible with the regular lyric line schema.
    """
    title, artist = clean_track_meta(request.args.get("title"), request.args.get("artist"))
    duration = request.args.get("duration") or ""
    try:
        syllables = fetch_netease_yrc(title, artist)
        if syllables:
            return jsonify({"source": "netease_yrc", "precise": True, "lines": syllables})

        raw_lines = []
        seconds = parse_duration(duration)
        params = {"track_name": title[:200], "artist_name": artist[:200]}
        if seconds is not None:
            params["duration"] = seconds
        try:
            query = urllib.parse.urlencode(params)
            with urllib.request.urlopen(f"https://lrclib.net/api/get?{query}", timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
            raw_lines = parse_lrc(payload.get("syncedLyrics", ""))
        except Exception:
            raw_lines = []

        if not raw_lines:
            client = get_yt()
            track_id = clean(request.args.get("track_id"))
            if client is not None and valid_video_id(track_id):
                try:
                    watch = client.get_watch_playlist(videoId=track_id, limit=1)
                    lyrics_ref = watch.get("lyrics", {})
                    lyrics_id = lyrics_ref.get("browseId") if isinstance(lyrics_ref, dict) else lyrics_ref
                    result = client.get_lyrics(lyrics_id) if lyrics_id and hasattr(client, "get_lyrics") else {}
                    raw_lines = parse_lrc((result or {}).get("lyrics", ""))
                except Exception:
                    raw_lines = []
        lines = build_cadence_lines(raw_lines, seconds)
        return jsonify({"source": "cadence", "precise": False, "lines": lines})
    except Exception:
        return jsonify({"source": "none", "precise": False, "lines": []})


def resolve_intro_offset(video_id, audio_duration=None, clean_title="", clean_artist=""):
    """Resolve a video intro offset through cheap-to-expensive fallbacks.

    The duration gate deliberately runs first. A companion upload that is
    within three seconds of the audio is the same studio cut for lyric timing;
    SponsorBlock producer tags and chapters must never shift those lyrics.
    """
    info = {}
    audio_seconds = parse_duration(audio_duration)

    # Resolve metadata before any external offset provider. This is both the
    # exact-match guard and the source of the later chapter/delta fallbacks.
    try:
        import yt_dlp
        options = {"quiet": True, "no_warnings": True, "noplaylist": True,
                   "skip_download": True, "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}}}
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False) or {}
    except Exception:
        info = {}

    try:
        video_seconds = float(info.get("duration")) if info.get("duration") is not None else None
        if video_seconds is not None and audio_seconds is not None:
            delta = abs(video_seconds - audio_seconds)
            if delta <= 3.0:
                return {"offset": 0.0, "source": "exact_match"}
    except (TypeError, ValueError):
        pass

    # Only non-exact uploads reach the intro waterfall.
    try:
        categories = urllib.parse.quote(json.dumps(["music_offtopic"], separators=(",", ":")))
        request = urllib.request.Request(
            f"https://sponsor.ajay.app/api/skipSegments?videoID={urllib.parse.quote(video_id)}&categories={categories}",
            headers={"User-Agent": "myriddim/1.0"},
        )
        with urllib.request.urlopen(request, timeout=2.5) as response:
            segments = json.loads(response.read().decode("utf-8"))
        for segment in segments if isinstance(segments, list) else []:
            start, end = segment.get("segment", [0, 0]) if isinstance(segment, dict) else (0, 0)
            if float(start) <= 5.0 and float(end) > float(start):
                return {"offset": round(float(end), 2), "source": "sponsorblock"}
    except Exception:
        pass

    try:
        chapters = info.get("chapters") or []
        if len(chapters) > 1:
            first = chapters[0] or {}
            title_lower = clean(first.get("title")).lower()
            if any(marker in title_lower for marker in ("intro", "skit", "scene", "dialogue", "prelude")):
                end = float(first.get("end_time") or 0)
                if end > 0:
                    return {"offset": round(end, 2), "source": "chapter"}
            second_title = clean(chapters[1].get("title")).lower()
            if first.get("end_time") and clean_title.lower() in second_title:
                return {"offset": round(float(first["end_time"]), 2), "source": "chapter"}
    except Exception:
        pass

    # Transcript matching is intentionally optional. yt-dlp's JSON3 caption
    # extraction is not reliable across all clients, so only use a transcript
    # adapter if a deployment has supplied one.
    try:
        transcript_loader = globals().get("get_youtube_transcript")
        sample_loader = globals().get("get_first_lyric_line")
        transcript = transcript_loader(video_id) if callable(transcript_loader) else []
        sample = sample_loader(clean_title, clean_artist) if callable(sample_loader) else ""
        if transcript and sample:
            sample = clean(sample).lower()
            for item in transcript[:15]:
                if sample in clean(item.get("text")).lower():
                    return {"offset": round(float(item.get("start") or 0), 2), "source": "transcript"}
    except Exception:
        pass

    try:
        video_seconds = float(info.get("duration")) if info.get("duration") is not None else None
        if video_seconds is not None and audio_seconds is not None:
            delta = video_seconds - audio_seconds
            if delta > 3.0:
                return {"offset": 0.0, "estimated_delta": round(delta, 2), "source": "delta_estimate"}
    except (TypeError, ValueError):
        pass
    return {"offset": 0.0, "source": "none"}


@app.get("/api/video-offset")
def get_video_offset():
    video_id = clean(request.args.get("video_id"))
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400
    try:
        with db_connection() as db:
            row = db.execute("SELECT video_id, intro_offset, source, estimated_delta FROM video_offsets WHERE video_id = ?", (video_id,)).fetchone()
        if row:
            # Manual calibrations are authoritative. Automatic offsets created
            # before the duration gate must be revalidated when the caller has
            # the audio duration, otherwise an old SponsorBlock result could
            # keep shifting an exact studio cut forever.
            has_duration = parse_duration(request.args.get("audio_duration")) is not None
            if row["source"] == "manual" or row["source"] == "exact_match" or not has_duration:
                return jsonify({"video_id": video_id, "intro_offset": row["intro_offset"], "source": row["source"], "estimated_delta": row["estimated_delta"], "cached": True})
    except sqlite3.Error:
        pass
    meta_title, meta_artist = clean_track_meta(request.args.get("title"), request.args.get("artist"))
    result = resolve_intro_offset(video_id, request.args.get("audio_duration"), meta_title, meta_artist)
    try:
        with db_connection() as db:
            db.execute("""INSERT INTO video_offsets(video_id, intro_offset, source, estimated_delta)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(video_id) DO UPDATE SET intro_offset=excluded.intro_offset,
                       source=excluded.source, estimated_delta=excluded.estimated_delta,
                       updated_at=CURRENT_TIMESTAMP""",
                       (video_id, result.get("offset", 0.0), result.get("source", "none"), result.get("estimated_delta")))
    except sqlite3.Error:
        pass
    return jsonify({"video_id": video_id, "intro_offset": result.get("offset", 0.0), "source": result.get("source", "none"), "estimated_delta": result.get("estimated_delta"), "cached": False})


@app.post("/api/video-offset")
def save_video_offset():
    body = request.get_json(silent=True) or {}
    video_id = clean(body.get("video_id"))
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400
    try:
        offset = float(body.get("intro_offset", 0))
        if not math.isfinite(offset) or offset < -30 or offset > 30:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "intro_offset must be between -30 and 30 seconds"}), 400
    source = clean(body.get("source")) or "manual"
    if source != "manual":
        source = "manual"
    try:
        with db_connection() as db:
            db.execute("""INSERT INTO video_offsets(video_id, intro_offset, source, estimated_delta)
                       VALUES (?, ?, ?, NULL)
                       ON CONFLICT(video_id) DO UPDATE SET intro_offset=excluded.intro_offset,
                       source=excluded.source, estimated_delta=NULL, updated_at=CURRENT_TIMESTAMP""",
                       (video_id, round(offset, 2), source))
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"video_id": video_id, "intro_offset": round(offset, 2), "source": source, "cached": True})


@app.post("/api/track/rate")
@rate_limit("rate", 20, 10)
def rate_track():
    """Set or clear the YouTube Music like for a track."""
    body = request.get_json(silent=True) or {}
    video_id = clean(body.get("video_id"))
    rating = clean(body.get("rating")).upper()
    if not valid_video_id(video_id) or rating not in ("LIKE", "DISLIKE", "INDIFFERENT"):
        return jsonify({"error": "Invalid video id or rating"}), 400
    try:
        from ytmusicapi.models.content.enums import LikeStatus
        require_yt().rate_song(video_id, LikeStatus[rating])
        return jsonify({"ok": True, "video_id": video_id, "rating": rating})
    except Exception as exc:
        return api_error(exc, 400)


@app.post("/api/track/listen")
@rate_limit("listen", 20, 10)
def record_listen():
    body = request.get_json(silent=True) or {}
    required = ["video_id", "title", "artist"]
    if any(not clean(body.get(key)) for key in required):
        return jsonify({"error": "video_id, title, and artist are required"}), 400
    if not valid_video_id(body.get("video_id")):
        return jsonify({"error": "Invalid video id"}), 400
    try:
        duration = max(30, int(body.get("listen_duration_seconds", 30)))
    except (TypeError, ValueError):
        duration = 30
    video_id = clean(body.get("video_id"))
    title = clean(body.get("title"))
    artist = clean(body.get("artist"))
    album = clean(body.get("album"))
    with db_connection() as db:
        canonical = ingest_track(
            db, source="youtube", source_id=video_id, title=title, artist=artist,
            # listen_duration_seconds is the amount heard, not the recording's
            # duration. Leave the matcher duration gate open for legacy clients.
            duration_sec=body.get("track_duration_seconds") or 0,
        )
        db.execute("""INSERT INTO listens
            (video_id, title, artist, album, thumbnail_url, played_at_timestamp,
             listen_duration_seconds, canonical_id, source, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'youtube', ?)""", (
            video_id, title, artist, album, body.get("thumbnail_url"),
            datetime.now(timezone.utc).isoformat(), duration, canonical, video_id))
    return jsonify({"ok": True, "canonical_id": canonical}), 201


@app.post("/api/stats/event")
@rate_limit("event", 30, 10)
def stats_event():
    """Local interaction event store: record a completed listen (>80%) or an
    early skip (<30s) for the recommendation engine. The UI already records a
    standard listen at the 30s mark via /api/track/listen; this endpoint adds
    the completion/skip signal on top of the same row's history.
    """
    body = request.get_json(silent=True) or {}
    video_id = clean(body.get("video_id"))
    event = clean(body.get("event")).lower()
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400
    if event not in ("completed", "skipped"):
        return jsonify({"error": "event must be 'completed' or 'skipped'"}), 400
    with db_connection() as db:
        # Attribute the event to the most recent listen row for this track so
        # per-track aggregates (play_count vs skip_count) stay row-aligned.
        row = db.execute("SELECT id FROM listens WHERE video_id = ? ORDER BY id DESC LIMIT 1", (video_id,)).fetchone()
        column = "completed" if event == "completed" else "skipped"
        if row is not None:
            db.execute(f"UPDATE listens SET {column} = 1 WHERE id = ?", (row["id"],))
        else:
            event_title = clean(body.get("title")) or "Unknown title"
            event_artist = clean(body.get("artist")) or "Unknown artist"
            canonical = ingest_track(
                db, source="youtube", source_id=video_id, title=event_title,
                artist=event_artist, duration_sec=body.get("track_duration_seconds") or 0,
            )
            db.execute("""INSERT INTO listens
                (video_id, title, artist, album, thumbnail_url, played_at_timestamp,
                 listen_duration_seconds, canonical_id, source, source_id, {0})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'youtube', ?, 1)""".format(column), (
                video_id, event_title, event_artist, clean(body.get("album")),
                body.get("thumbnail_url"), datetime.now(timezone.utc).isoformat(),
                max(0, int(body.get("listen_duration_seconds") or 0)), canonical, video_id))
    return jsonify({"ok": True}), 201


def preference_scores(db=None):
    """Score listening history once per canonical recording, not per source.

    Legacy rows without a canonical link still fall back to their YouTube id;
    startup migration links existing rows before this query is normally used.
    """
    query = """SELECT COALESCE(canonical_id, video_id) canonical_id,
        MAX(video_id) video_id, MAX(title) title, MAX(artist) artist, MAX(album) album,
        MAX(thumbnail_url) thumbnail_url, COUNT(*) plays,
        SUM(completed) completions, SUM(skipped) skips,
        SUM(CASE WHEN played_at_timestamp >= ? THEN 1 ELSE 0 END) recent_plays,
        MAX(played_at_timestamp) last_played
        FROM listens GROUP BY COALESCE(canonical_id, video_id)"""
    own = db is None
    if own:
        with db_connection() as connection:
            return preference_scores(connection)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    rows = db.execute(query, (cutoff,)).fetchall()
    return rows


def score_rows(rows):
    """Apply the weighted heuristic to aggregate rows: plays*2 - skips*5 plus
    a recency boost. Returns tracks sorted by score descending."""
    scored = []
    for row in rows:
        normalized = normalize_track({
            "videoId": row["video_id"], "title": row["title"], "artist": row["artist"],
            "album": row["album"], "thumbnail": row["thumbnail_url"],
        })
        if not normalized:
            continue
        plays, skips = row["plays"] or 0, row["skips"] or 0
        recent = row["recent_plays"] or 0
        completions = row["completions"] or 0
        # Completion is a strong positive signal; skips are a strong negative.
        score = plays * 2 - skips * 5 + completions * 3 + recent
        scored.append({"canonicalId": row["canonical_id"], "videoId": normalized["videoId"], "title": normalized["title"], "artist": normalized["artist"],
                       "album": row["album"], "thumbnail": normalized["thumbnail"], "plays": plays,
                       "skips": skips, "score": score, "last_played": row["last_played"]})
    return sorted(scored, key=lambda item: item["score"], reverse=True)


def stat_track(row):
    """Normalize a SQLite listen row before exposing it as a playable card."""
    normalized = normalize_track({
        "videoId": row["video_id"],
        "title": row["title"],
        "artist": row["artist"],
        "album": row["album"],
        "thumbnail": row["thumbnail_url"] if "thumbnail_url" in row.keys() else row["thumbnail"],
    })
    if not normalized:
        return None
    return {"videoId": normalized["videoId"], "id": normalized["videoId"],
            "title": normalized["title"], "artist": normalized["artist"],
            "album": clean(row["album"]), "thumbnail": normalized["thumbnail"]}

@app.get("/api/stats/monthly-top")
def monthly_top():
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with db_connection() as db:
        rows = db.execute("""SELECT video_id, MAX(title) title, MAX(artist) artist, MAX(album) album,
            MAX(thumbnail_url) thumbnail_url, COUNT(*) plays, SUM(listen_duration_seconds) seconds
            FROM listens WHERE played_at_timestamp LIKE ? GROUP BY video_id ORDER BY plays DESC, seconds DESC LIMIT 25""", (month + "%",)).fetchall()
        all_time = db.execute("""SELECT video_id, MAX(title) title, MAX(artist) artist, MAX(album) album,
            MAX(thumbnail_url) thumbnail_url, COUNT(*) plays, SUM(listen_duration_seconds) seconds
            FROM listens GROUP BY video_id ORDER BY plays DESC, seconds DESC LIMIT 25""").fetchall()
        total = db.execute("SELECT COALESCE(SUM(listen_duration_seconds), 0) FROM listens WHERE played_at_timestamp LIKE ?", (month + "%",)).fetchone()[0]
    return jsonify({"month": month, "totalMinutes": round(total / 60), "monthly": [dict(track, plays=row["plays"]) for row in rows if (track := stat_track(row))],
                    "heavyRotation": [dict(track, plays=row["plays"]) for row in all_time if (track := stat_track(row))]})

@app.get("/api/stats/analytics")
def stats_analytics():
    """Return the native listening dashboard's range-aware aggregates.

    Analytics stay entirely local: the only source is the user's SQLite
    ``listens`` table. ``range`` is deliberately an allowlist so the date
    window can never become SQL input.
    """
    ranges = {"7": 7, "30": 30, "180": 180, "all": None}
    range_name = clean(request.args.get("range") or "30").lower()
    if range_name not in ranges:
        return jsonify({"error": "range must be one of: 7, 30, 180, all"}), 400

    days = ranges[range_name]
    where, params = "", []
    if days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        where, params = " WHERE played_at_timestamp >= ?", [cutoff]

    try:
        with db_connection() as db:
            metrics = db.execute(f"""SELECT
                COALESCE(SUM(listen_duration_seconds), 0) total_seconds,
                COUNT(*) total_tracks,
                COUNT(DISTINCT NULLIF(TRIM(artist), '')) unique_artists
                FROM listens{where}""", params).fetchone()

            artist_rows = db.execute(f"""SELECT COALESCE(NULLIF(TRIM(artist), ''), 'Unknown artist') artist,
                COUNT(*) plays, COALESCE(SUM(listen_duration_seconds), 0) seconds
                FROM listens{where} GROUP BY artist ORDER BY plays DESC, seconds DESC LIMIT 10""", params).fetchall()

            track_rows = db.execute(f"""SELECT video_id, MAX(title) title, MAX(artist) artist,
                MAX(album) album, MAX(thumbnail_url) thumbnail, COUNT(*) plays,
                COALESCE(SUM(listen_duration_seconds), 0) seconds
                FROM listens{where} GROUP BY video_id
                ORDER BY plays DESC, seconds DESC LIMIT 10""", params).fetchall()

            trend_rows = db.execute(f"""SELECT date(played_at_timestamp) date,
                COALESCE(SUM(listen_duration_seconds), 0) seconds, COUNT(*) plays
                FROM listens{where} GROUP BY date(played_at_timestamp) ORDER BY date ASC""", params).fetchall()

            heatmap_rows = db.execute(f"""SELECT CAST(strftime('%w', played_at_timestamp) AS INTEGER) day,
                CAST(strftime('%H', played_at_timestamp) AS INTEGER) hour, COUNT(*) intensity
                FROM listens{where} GROUP BY day, hour ORDER BY day, hour""", params).fetchall()

        return jsonify({
            "range": range_name,
            "since": cutoff if days is not None else None,
            "metrics": {
                "totalSeconds": metrics["total_seconds"] or 0,
                "totalTracks": metrics["total_tracks"] or 0,
                "uniqueArtists": metrics["unique_artists"] or 0,
            },
            "topArtists": [dict(row) for row in artist_rows],
            "topTracks": [dict(track, plays=row["plays"], seconds=row["seconds"])
                          for row in track_rows if (track := stat_track(row))],
            "trend": [dict(row) for row in trend_rows],
            "heatmap": [dict(row) for row in heatmap_rows],
        })
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


def canonical_source_metadata(db, canonical_ids):
    """Return provider labels for canonical recommendation badges."""
    ids = [str(value) for value in canonical_ids if value]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = db.execute(
        f"SELECT canonical_id, source FROM track_sources WHERE canonical_id IN ({placeholders}) GROUP BY canonical_id, source",
        ids,
    ).fetchall()
    result = {value: [] for value in ids}
    for row in rows:
        result.setdefault(str(row["canonical_id"]), []).append(row["source"])
    return result


@app.get("/api/recommendations/smart-mix")
def smart_mix():
    """Local recommendation engine: score the user's own history (plays,
    completions, skips, recency), then build a Personal Mix — top tracks by
    preference score, plus discovery seeds from those users' favorite artists
    via ytmusicapi when a session is available.
    """
    with db_connection() as db:
        scored = score_rows(preference_scores(db))
        source_map = canonical_source_metadata(db, [track.get("canonicalId") for track in scored])
    favorites = [track for track in scored if track["skips"] * 5 < track["plays"] * 2][:30]
    mix = []
    seen = set()
    for track in favorites:
        canonical = track.get("canonicalId") or track["videoId"]
        if canonical in seen:
            continue
        seen.add(canonical)
        mix.append({"canonicalId": canonical, "videoId": track["videoId"], "title": track["title"], "artist": track["artist"],
                    "album": track["album"], "thumbnail": track["thumbnail"], "score": track["score"],
                    "available_sources": source_map.get(str(canonical), ["youtube"])})
    # Discovery: pull related tracks for the highest-scored seed via the watch
    # playlist when authenticated, capped so the mix stays dominated by the
    # user's own taste.
    discovery = []
    client = get_yt()
    if client is not None and favorites:
        seed = favorites[0]["videoId"]
        try:
            watch = client.get_watch_playlist(videoId=seed, limit=15) or {}
            with db_connection() as db:
                for item in watch.get("tracks", []) or []:
                    video_id = clean(item.get("videoId"))
                    if not valid_video_id(video_id):
                        continue
                    track = track_data(item)
                    if not track or not track.get("videoId"):
                        continue
                    canonical = ingest_track(
                        db, source="youtube", source_id=video_id,
                        title=track["title"], artist=track["artist"],
                        duration_sec=parse_duration(track.get("duration")) or 0,
                    )
                    if canonical in seen:
                        continue
                    discovery.append({**track, "canonicalId": canonical,
                                      "available_sources": ["youtube"]})
                    seen.add(canonical)
                    if len(discovery) >= 10:
                        break
        except Exception as exc:
            print(f"Smart mix discovery failed: {exc}", flush=True)
    return jsonify({"mix": mix, "discovery": discovery, "source": "local_history"})


@app.get("/api/soundcloud/search")
def soundcloud_search():
    """Search SoundCloud when a client id is configured."""
    query = clean(request.args.get("q"))[:120]
    if not query:
        return jsonify({"tracks": []})
    provider = SoundCloudProvider()
    if not provider.enabled:
        return jsonify({"error": "SoundCloud is not configured", "tracks": []}), 503
    try:
        return jsonify({"tracks": provider.search(query, request.args.get("limit", 20))})
    except Exception as exc:
        return jsonify({"error": str(exc), "tracks": []}), 502


@app.post("/api/soundcloud/sync")
def soundcloud_sync():
    """Ingest SoundCloud likes, reposts, and playlist tracks into the catalog."""
    provider = SoundCloudProvider()
    if not provider.enabled or not provider.oauth_token:
        return jsonify({"error": "SoundCloud client id and OAuth token are required"}), 503
    try:
        saved = provider.get_user_saved()
        created = 0
        reviews = 0
        with db_connection() as db:
            for track in saved:
                before = db.execute("SELECT 1 FROM track_sources WHERE source = 'soundcloud' AND source_id = ?", (track["source_id"],)).fetchone()
                ingest_track(db, source="soundcloud", source_id=track["source_id"],
                             title=track["title"], artist=track["artist"],
                             duration_sec=track["duration_sec"], isrc=track.get("isrc"),
                             stream_url=None)
                created += before is None
            reviews = db.execute("SELECT COUNT(*) FROM merge_review_queue WHERE status = 'pending'").fetchone()[0]
        return jsonify({"ok": True, "ingested": created, "total": len(saved), "pending_reviews": reviews})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 502


def build_smart_playlist_query(rules, limit=50):
    """Compile validated smart-playlist rules into SQL and bound parameters.

    Column names and operators are allowlisted; every user value remains a
    SQLite parameter. The same compiler powers preview and saved recipes.
    """
    if not isinstance(rules, list) or not rules:
        raise ValueError("rules must be a non-empty list")
    fields = {"video_id", "title", "artist", "album", "play_count", "skips", "bpm", "energy", "valence", "last_played"}
    ops = {"=", "!=", "<", ">", "<=", ">=", "LIKE"}
    try:
        limit = min(max(int(limit), 1), 200)
    except (TypeError, ValueError):
        limit = 50
    sql = "SELECT video_id, MAX(title) title, MAX(artist) artist, MAX(album) album, MAX(thumbnail_url) thumbnail_url, COUNT(*) plays, SUM(skipped) skips FROM listens WHERE 1=1"
    params = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        field, op, value = clean(rule.get("field")), str(rule.get("op") or "").upper(), rule.get("val")
        if field not in fields or op not in ops:
            continue
        if field in ("play_count", "skips", "last_played"):
            continue
        if field in ("title", "artist", "album", "video_id"):
            sql += f" AND {field} {op} ?"
            # The UI presents LIKE as a human-friendly “contains” rule.
            params.append(f"%{value}%" if op == "LIKE" else value)
    sql += " GROUP BY video_id"
    having = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        field, op, value = clean(rule.get("field")), str(rule.get("op") or "").upper(), rule.get("val")
        if field == "play_count" and op in ops:
            having.append(f"COUNT(*) {op} ?")
            params.append(value)
        elif field == "skips" and op in ops:
            having.append(f"SUM(skipped) {op} ?")
            params.append(value)
        elif field == "last_played" and op in ops:
            having.append(f"(MAX(played_at_timestamp) IS NOT NULL AND MAX(played_at_timestamp) {op} datetime('now', ?))")
            params.append(str(value))
    if having:
        sql += " HAVING " + " AND ".join(having)
    sql += " ORDER BY RANDOM() LIMIT ?"
    params.append(limit)
    return sql, params


@app.post("/api/playlists/smart")
def smart_playlist():
    """Evaluate an unsaved smart-playlist recipe against local history."""
    body = request.get_json(silent=True) or {}
    rules = body.get("rules")
    try:
        sql, params = build_smart_playlist_query(rules, body.get("limit", 50))
        with db_connection() as db:
            rows = db.execute(sql, params).fetchall()
        return jsonify({"tracks": [dict(track, plays=row["plays"]) for row in rows if (track := stat_track(row))], "rules": rules})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/playlists/smart/save")
def save_smart_playlist():
    """Persist a validated local smart-playlist recipe."""
    body = request.get_json(silent=True) or {}
    name = clean(body.get("name"))[:120]
    rules = body.get("rules")
    try:
        build_smart_playlist_query(rules, body.get("limit", 50))
        if not name:
            raise ValueError("A playlist name is required")
        try:
            limit = min(max(int(body.get("limit", 50)), 1), 200)
        except (TypeError, ValueError):
            limit = 50
        with db_connection() as db:
            cursor = db.execute("INSERT INTO smart_playlists (name, rules_json, track_limit) VALUES (?, ?, ?)",
                                (name, json.dumps(rules), limit))
            playlist_id = cursor.lastrowid
        return jsonify({"id": playlist_id, "name": name, "rules": rules, "limit": limit}), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/playlists/smart")
def list_smart_playlists():
    with db_connection() as db:
        rows = db.execute("SELECT id, name, rules_json, track_limit, created_at FROM smart_playlists ORDER BY created_at DESC, id DESC").fetchall()
    return jsonify([{"id": row["id"], "name": row["name"], "rules": json.loads(row["rules_json"]),
                     "limit": row["track_limit"], "created_at": row["created_at"]} for row in rows])


@app.get("/api/playlists/smart/<int:playlist_id>/tracks")
def evaluate_smart_playlist(playlist_id):
    with db_connection() as db:
        row = db.execute("SELECT rules_json, track_limit FROM smart_playlists WHERE id = ?", (playlist_id,)).fetchone()
    if not row:
        return jsonify({"error": "Smart playlist not found"}), 404
    try:
        rules = json.loads(row["rules_json"])
        sql, params = build_smart_playlist_query(rules, row["track_limit"])
        with db_connection() as db:
            tracks = db.execute(sql, params).fetchall()
        return jsonify({"id": playlist_id, "tracks": [dict(track, plays=track_row["plays"]) for track_row in tracks if (track := stat_track(track_row))], "rules": rules})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.delete("/api/playlists/smart/<int:playlist_id>")
def delete_smart_playlist(playlist_id):
    with db_connection() as db:
        deleted = db.execute("DELETE FROM smart_playlists WHERE id = ?", (playlist_id,)).rowcount
    return jsonify({"success": deleted > 0})

@app.get("/api/stats/export")
def export_stats():
    """Dump every recorded listen as JSON for the user to download."""
    with db_connection() as db:
        rows = db.execute("SELECT * FROM listens ORDER BY played_at_timestamp").fetchall()
    return jsonify({"exported_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(rows),
                    "listens": [dict(row) for row in rows]})

@app.get("/api/home/quick-picks")
def quick_picks():
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        shelves = client.get_home() or []
        tracks = []
        for shelf in shelves:
            title = clean(shelf.get("title"))
            for item in shelf.get("contents", []):
                track = track_data(item)
                if track and ("quick" in title.lower() or not tracks):
                    tracks.append(track)
                if len(tracks) >= 12:
                    break
            if len(tracks) >= 12:
                break
        payload = {"title": "Quick Picks", "tracks": tracks}
        # Same silent-empty trap as the library: a lapsed session yields an empty
        # home feed. Serve the last healthy shelf instead of a hollow Discover view.
        if not tracks and session_state() == "expired":
            cached = load_library_cache("quick_picks")
            if cached is not None:
                return jsonify({**cached, "cached": True})
        save_library_cache("quick_picks", payload)
        return jsonify(payload)
    except Exception as exc:
        return api_error(exc)

@app.get("/api/recommendations")
@rate_limit("recommendations", 12, 10)
def recommendations():
    video_id = clean(request.args.get("video_id"))
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id", "tracks": []}), 400
    client = get_yt()
    if client is None:
        return jsonify({"tracks": []})
    try:
        watch = client.get_watch_playlist(videoId=video_id, limit=20) or {}
        tracks, seen = [], {video_id}
        for item in watch.get("tracks", []) or []:
            candidate_id = clean(item.get("videoId"))
            if not valid_video_id(candidate_id) or candidate_id in seen:
                continue
            track = track_data(item)
            if not track:
                continue
            seen.add(candidate_id)
            tracks.append(track)
            if len(tracks) >= 12:
                break
        return jsonify({"tracks": tracks, "source": "watch_playlist"})
    except Exception as exc:
        traceback.print_exc()
        print(f"Recommendations failed for video_id={video_id!r}: {exc}", flush=True)
        return jsonify({"error": str(exc), "tracks": []}), 502

@app.get("/api/mix/<video_id>")
@rate_limit("mix", 6, 30)
def track_mix(video_id):
    """Build a fresh radio queue from one exact YouTube Music track."""
    video_id = clean(video_id)
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id", "seed_id": video_id, "tracks": []}), 400
    client = get_yt()
    if client is None:
        return jsonify({"error": "ytmusicapi is not available", "seed_id": video_id, "tracks": []}), 502
    try:
        radio = client.get_watch_playlist(videoId=video_id, radio=True, limit=25) or {}
        tracks = normalize_radio_tracks(radio.get("tracks"), track_data, valid_video_id)
        return jsonify({"seed_id": video_id, "tracks": tracks}), 200
    except Exception as exc:
        traceback.print_exc()
        print(f"Mix generation failed for video_id={video_id!r}: {exc}", flush=True)
        return jsonify({"error": str(exc), "seed_id": video_id, "tracks": []}), 502

# --- Discovery engine: 60/40 fresh/familiar blend with history exclusion ---
DISCOVERY_CACHE = {}
DISCOVERY_CACHE_TTL = 300


def _discovery_history(db):
    """Tracks fatigued by repetition (2+ plays) or freshness (heard in the
    last 7 days). These IDs are blacklisted from the discovery pool."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows = db.execute(
        "SELECT video_id FROM listens GROUP BY video_id "
        "HAVING COUNT(*) >= 2 OR MAX(played_at_timestamp) >= ?",
        (cutoff,),
    ).fetchall()
    return {row["video_id"] for row in rows}


def _discovery_top_artists(db, limit):
    rows = db.execute(
        "SELECT artist FROM listens WHERE TRIM(artist) != '' "
        "GROUP BY artist ORDER BY COUNT(*) DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [row["artist"] for row in rows]


def _discovery_artist_plays(db, artist_name):
    row = db.execute(
        "SELECT COUNT(*) plays FROM listens WHERE artist = ?", (artist_name,)
    ).fetchone()
    return row["plays"] if row else 0


@app.get("/api/recommendations/discover")
@rate_limit("discover", 4, 60)
def discovery_shelf():
    """Hybrid recommendation shelf: 60% unheard discoveries (native YTM radio
    + one-hop related-artist traversal) and 40% familiar ground (unplayed
    deep cuts from favorite artists), interleaved 2:1.
    """
    seed_id = clean(request.args.get("seed_track_id"))
    if seed_id and not valid_video_id(seed_id):
        return jsonify({"error": "Invalid seed track id", "recommendations": []}), 400
    cache_key = seed_id or "no-seed"
    cached = DISCOVERY_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < DISCOVERY_CACHE_TTL:
        return jsonify({"recommendations": cached[1], "cached": True})
    client = get_yt()
    if client is None:
        return jsonify({"recommendations": []})
    discovery, familiar, seen = [], [], set()
    try:
        with db_connection() as db:
            seen.update(_discovery_history(db))
            if seed_id:
                seen.add(seed_id)
            # 1. Native radio seeded by the current track; YouTube's own
            # collaborative filtering does the exploration, we only filter
            # out what the user already knows.
            if seed_id:
                try:
                    watch = client.get_watch_playlist(videoId=seed_id, radio=True, limit=25) or {}
                    for item in watch.get("tracks", []) or []:
                        track = track_data(item)
                        if not track or track["videoId"] in seen:
                            continue
                        track["discovery_source"] = "discovery_radio"
                        seen.add(track["videoId"])
                        discovery.append(track)
                except Exception as exc:
                    print(f"Discovery radio failed for {seed_id}: {exc}", flush=True)

            # 2. One-hop related-artist traversal: same sonic space as the
            # user's top artists, but artists with little local play history.
            for artist_name in _discovery_top_artists(db, 3)[:3]:
                if len(discovery) >= 12:
                    break
                try:
                    matches = client.search(artist_name, filter="artists", limit=1) or []
                    if not matches or not matches[0].get("browseId"):
                        continue
                    artist_data = client.get_artist(matches[0]["browseId"]) or {}
                    related = (artist_data.get("related") or {}).get("results", []) or []
                    for related_artist in related[:4]:
                        related_name = clean(related_artist.get("title"))
                        if not related_name or _discovery_artist_plays(db, related_name) >= 2:
                            continue
                        songs = client.search(f"{related_name} top tracks", filter="songs", limit=4) or []
                        for item in songs:
                            track = track_data(item)
                            if not track or track["videoId"] in seen:
                                continue
                            track["discovery_source"] = "related_artist"
                            track["related_to"] = artist_name
                            seen.add(track["videoId"])
                            discovery.append(track)
                            if len(discovery) >= 12:
                                break
                        if len(discovery) >= 12:
                            break
                except Exception as exc:
                    print(f"Related-artist traversal failed for {artist_name}: {exc}", flush=True)

            # 3. Familiar ground: unplayed tracks from the user's top artists.
            for artist_name in _discovery_top_artists(db, 5)[:5]:
                if len(familiar) >= 8:
                    break
                try:
                    songs = client.search(artist_name, filter="songs", limit=6) or []
                    for item in songs:
                        track = track_data(item)
                        if not track or track["videoId"] in seen:
                            continue
                        track["discovery_source"] = "familiar_deep_cut"
                        seen.add(track["videoId"])
                        familiar.append(track)
                        if len(familiar) >= 8:
                            break
                except Exception as exc:
                    print(f"Familiar search failed for {artist_name}: {exc}", flush=True)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc), "recommendations": []}), 502
    # Interleave 2 discoveries per familiar deep cut (the 60/40 split).
    combined, di, fi = [], 0, 0
    while len(combined) < 20 and (di < len(discovery) or fi < len(familiar)):
        if di < len(discovery):
            combined.append(discovery[di]); di += 1
        if di < len(discovery) and len(combined) < 20:
            combined.append(discovery[di]); di += 1
        if fi < len(familiar):
            combined.append(familiar[fi]); fi += 1
    combined = combined[:20]
    DISCOVERY_CACHE[cache_key] = (time.time(), combined)
    return jsonify({"recommendations": combined})


@app.get("/api/account")
def account():
    """Report which Google account the active credentials belong to, so the
    UI can verify the browser.json tokens map to the primary listening
    profile (strict account alignment) instead of silently serving a
    different profile's personalized data.
    """
    client = get_yt()
    if client is None:
        return jsonify({"authenticated": False, "account": None})
    try:
        info = client.get_account_info() or {}
        return jsonify({"authenticated": True,
                        "account": {"name": clean(info.get("accountName")),
                                    "handle": clean(info.get("channelHandle")),
                                    "photo": clean(info.get("accountPhotoUrl"))}})
    except Exception as exc:
        return jsonify({"authenticated": False, "account": None, "error": str(exc)}), 502


@app.post("/api/scrobble")
@rate_limit("scrobble", 6, 10)
def scrobble():
    """Report a finished listen back to YouTube Music's watch history, the
    signal the recommendation engine actually learns from. Mirrors
    ytmusicapi's documented flow: get_song() -> add_history_item(); 204
    means YouTube accepted the report.
    """
    body = request.get_json(silent=True) or {}
    video_id = clean(body.get("video_id"))
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id", "scrobbled": False}), 400
    client = get_yt()
    if client is None:
        return jsonify({"error": "ytmusicapi is not available", "scrobbled": False}), 502
    try:
        song = client.get_song(video_id)
        if not isinstance(song, dict) or not song.get("playbackTracking"):
            return jsonify({"error": "No playback tracking url in response", "scrobbled": False}), 422
        response = client.add_history_item(song)
        accepted = getattr(response, "status_code", None) == 204
        return jsonify({"scrobbled": accepted, "status": getattr(response, "status_code", None)})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc), "scrobbled": False}), 502


@app.get("/api/discover")
@rate_limit("discover", 6, 10)
def discover():
    """Full personalized home feed: every shelf (Quick Picks, mixes,
    community mixes) as returned by get_home(), instead of the flattened
    quick-picks subset. Lets the frontend render true discovery shelves.
    """
    client = get_yt()
    if client is None:
        return jsonify({"shelves": []})
    try:
        shelves = []
        for shelf in (client.get_home(limit=10) or []):
            title = clean(shelf.get("title"))
            tracks = []
            for item in (shelf.get("contents") or []):
                track = track_data(item)
                if track and track.get("videoId"):
                    tracks.append(track)
            if tracks:
                shelves.append({"title": title, "tracks": tracks})
        return jsonify({"shelves": shelves})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc), "shelves": []}), 502


@app.get("/api/moods")
@rate_limit("moods", 6, 10)
def moods():
    """Mood & genre categories ("Moods & Genres" hub): sections mapped to
    category chips carrying the params needed to load each mood's playlists.
    """
    client = get_yt()
    if client is None:
        return jsonify({"sections": []})
    try:
        data = client.get_mood_categories() or {}
        sections = []
        for section_title, categories in data.items():
            chips = []
            for category in (categories or []):
                if isinstance(category, dict) and category.get("params"):
                    chips.append({"title": clean(category.get("title")), "params": category.get("params")})
            if chips:
                sections.append({"title": clean(section_title), "categories": chips})
        return jsonify({"sections": sections})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc), "sections": []}), 502


@app.get("/api/moods/playlists")
@rate_limit("moods", 6, 10)
def mood_playlists():
    """Playlists for one mood/genre category, addressed by the params token
    from /api/moods.
    """
    params = clean(request.args.get("params"))
    if not params:
        return jsonify({"error": "Missing params", "playlists": []}), 400
    client = get_yt()
    if client is None:
        return jsonify({"playlists": []})
    try:
        playlists = []
        for item in (client.get_mood_playlists(params) or [])[:24]:
            playlists.append({"browseId": clean(item.get("playlistId") or item.get("browseId")), "title": clean(item.get("title")),
                              "thumbnail": thumbnail(item.get("thumbnails")), "count": clean(item.get("count"))})
        return jsonify({"playlists": playlists})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc), "playlists": []}), 502


def artist_release(item):
    """Normalize an album/single card from an artist page."""
    return {"browseId": clean(item.get("browseId")), "title": clean(item.get("title")),
            "year": clean(item.get("year")), "type": clean(item.get("type")),
            "thumbnail": thumbnail(item.get("thumbnails"))}

def _artist_payload(client, browse_id):
    data = client.get_artist(browse_id) or {}
    def section(shelf):
        shelf = shelf or {}
        return shelf.get("results") or shelf.get("contents") or []
    return {
        "browseId": browse_id,
        "name": clean(data.get("name")),
        "description": clean(data.get("description")),
        "subscribers": clean(data.get("subscribers")),
        "views": clean(data.get("views")),
        "thumbnail": thumbnail(data.get("thumbnails")),
        "songs": [track for item in section(data.get("songs")) if (track := track_data(item))],
        "albums": [artist_release(item) for item in section(data.get("albums")) if item.get("browseId")],
        "singles": [artist_release(item) for item in section(data.get("singles")) if item.get("browseId")],
    }


def _album_payload(client, browse_id):
    data = client.get_album(browse_id) or {}
    artists = data.get("artists") or data.get("artist") or []
    if isinstance(artists, dict):
        artists = [artists]
    artist_name = ", ".join(clean(a.get("name")) for a in artists if isinstance(a, dict) and a.get("name"))
    artist_id = next((clean(a.get("id")) for a in artists if isinstance(a, dict) and a.get("id")), None)
    tracks = [track for item in (data.get("tracks") or []) if (track := track_data(item))]
    return {
        "browseId": browse_id,
        "title": clean(data.get("title")),
        "type": clean(data.get("type")),
        "description": clean(data.get("description")),
        "artist": artist_name,
        "artistId": artist_id,
        "year": clean(data.get("year")),
        "trackCount": data.get("trackCount") or len(tracks),
        "durationSeconds": data.get("duration_seconds"),
        "audioPlaylistId": clean(data.get("audioPlaylistId")),
        "thumbnail": thumbnail(data.get("thumbnails")),
        "tracks": tracks,
    }


# --- Entity navigation: resolve a name or raw id to a full artist/album page ---
@app.get("/api/artist/resolve")
@rate_limit("browse", 12, 10)
def artist_resolve():
    query = clean(request.args.get("q"))
    if not query:
        return jsonify({"error": "Missing artist query"}), 400
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    browse_id = query if valid_browse_id(query) else None
    if not browse_id:
        try:
            matches = client.search(query, filter="artists", limit=1) or []
            if matches and matches[0].get("browseId"):
                browse_id = matches[0]["browseId"]
        except Exception as exc:
            traceback.print_exc()
            return jsonify({"error": str(exc)}), 502
    if not browse_id:
        return jsonify({"error": f"Could not find artist '{query}'"}), 404
    try:
        return jsonify(_artist_payload(client, browse_id))
    except Exception as exc:
        traceback.print_exc()
        print(f"Artist resolve failed for {query!r}: {exc}", flush=True)
        return jsonify({"error": str(exc)}), 500


@app.get("/api/album/resolve")
@rate_limit("browse", 12, 10)
def album_resolve():
    title = clean(request.args.get("title"))
    artist = clean(request.args.get("artist"))
    if not title:
        return jsonify({"error": "Missing album query"}), 400
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    browse_id = title if valid_browse_id(title) else None
    if not browse_id:
        query = f"{artist} {title}".strip() if artist else title
        try:
            matches = client.search(query, filter="albums", limit=1) or []
            if matches and matches[0].get("browseId"):
                browse_id = matches[0]["browseId"]
        except Exception as exc:
            traceback.print_exc()
            return jsonify({"error": str(exc)}), 502
    if not browse_id:
        return jsonify({"error": f"Could not find album '{title}'"}), 404
    try:
        return jsonify(_album_payload(client, browse_id))
    except Exception as exc:
        traceback.print_exc()
        print(f"Album resolve failed for {title!r}: {exc}", flush=True)
        return jsonify({"error": str(exc)}), 500


@app.get("/api/artists/favorites")
def favorite_artists_list():
    with db_connection() as db:
        rows = db.execute("SELECT id, name, thumbnail FROM favorite_artists ORDER BY created_at DESC").fetchall()
        return jsonify({"artists": [{"id": row["id"], "name": row["name"], "thumbnail": row["thumbnail"]} for row in rows]})


@app.post("/api/artists/favorite")
def toggle_favorite_artist():
    payload = request.get_json(silent=True) or {}
    artist_id = clean(payload.get("id"))
    name = clean(payload.get("name"))
    if not artist_id or not name:
        return jsonify({"error": "Artist id and name are required"}), 400
    with db_connection() as db:
        exists = db.execute("SELECT 1 FROM favorite_artists WHERE id = ?", (artist_id,)).fetchone()
        if exists:
            db.execute("DELETE FROM favorite_artists WHERE id = ?", (artist_id,))
            favorited = False
        else:
            db.execute("INSERT OR REPLACE INTO favorite_artists (id, name, thumbnail) VALUES (?, ?, ?)",
                       (artist_id, name, clean(payload.get("thumbnail"))))
            favorited = True
        return jsonify({"favorited": favorited, "artist": {"id": artist_id, "name": name}})


@app.get("/api/home/stats-rotation")
def stats_rotation():
    """Top tracks by completion count over the last 30 days (local listens table)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with db_connection() as db:
        rows = db.execute(
            """SELECT video_id, title, artist, album, thumbnail_url, COUNT(*) plays
               FROM listens WHERE completed = 1 AND played_at_timestamp >= ? AND video_id != ''
               GROUP BY video_id ORDER BY plays DESC, MAX(played_at_timestamp) DESC LIMIT 15""",
            (cutoff,)).fetchall()
        tracks = [track for row in rows if (track := stat_track(row))]
        return jsonify({"tracks": tracks})


@app.get("/api/playlists/recent")
def recent_playlists():
    with db_connection() as db:
        rows = db.execute(
            "SELECT playlist_id, title, thumbnail, track_count FROM playlist_history ORDER BY last_played DESC LIMIT 3"
        ).fetchall()
        return jsonify({"playlists": [{"id": row["playlist_id"], "title": row["title"],
                                        "thumbnail": row["thumbnail"], "count": row["track_count"]} for row in rows]})


@app.get("/api/ytm/feed")
@rate_limit("ytm-feed", 6, 15)
def ytm_feed():
    """Proxy YouTube Music's native multi-shelf home feed (Quick picks, From
    the community, etc.) so the Discover view shows the same personalized
    shelves as the YouTube Music web interface."""
    client = get_yt()
    if client is None:
        return jsonify({"error": "Not authenticated", "shelves": []}), 401
    try:
        feed = client.get_home(limit=8)
        shelves = []
        for shelf in feed or []:
            contents = shelf.get("contents") or []
            if not contents:
                continue
            items = []
            for item in contents:
                if not isinstance(item, dict):
                    continue
                video_id = clean(item.get("videoId"))
                playlist_id = clean(item.get("playlistId"))
                browse_id = clean(item.get("browseId"))
                item_type = "song" if video_id else ("playlist" if (playlist_id or browse_id) else "item")

                if item_type == "song":
                    track = track_data(item)
                    if not track:
                        continue
                    items.append({
                        "id": track["videoId"],
                        "type": "song",
                        "title": track["title"],
                        "subtitle": track["artist"],
                        "thumbnail": track["thumbnail"],
                        "track_count": item.get("itemCount"),
                        "views": item.get("views"),
                    })
                    continue

                title = clean(_field_text(item.get("title")) or _field_text(item.get("name")))
                item_id = playlist_id or browse_id
                if not title or not item_id:
                    continue
                items.append({
                    "id": item_id,
                    "type": item_type,
                    "title": title,
                    "subtitle": clean(_first_artist(item.get("artists") or item.get("author"))) or clean(_field_text(item.get("description"))),
                    "thumbnail": _thumbnail_url(item.get("thumbnails") or item.get("thumbnail")),
                    "track_count": item.get("itemCount"),
                    "views": item.get("views"),
                })
            if items:
                shelves.append({"title": shelf.get("title") or "Discover",
                                "strapline": shelf.get("strapline") or "", "items": items})
        return jsonify({"shelves": shelves}), 200
    except Exception as exc:
        traceback.print_exc()
        print(f"YTM feed failed: {exc}", flush=True)
        return jsonify({"error": str(exc), "shelves": []}), 502


@app.get("/api/artist/<browse_id>")
@rate_limit("browse", 12, 10)
def artist_page(browse_id):
    browse_id = clean(browse_id)
    if not valid_browse_id(browse_id):
        return jsonify({"error": "Invalid browse id"}), 400
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        return jsonify(_artist_payload(client, browse_id))
    except Exception as exc:
        traceback.print_exc()
        print(f"Artist page failed for browse_id={browse_id!r}: {exc}", flush=True)
        return jsonify({"error": str(exc)}), 500

@app.get("/api/album/<browse_id>")
@rate_limit("browse", 12, 10)
def album_page(browse_id):
    browse_id = clean(browse_id)
    if not valid_browse_id(browse_id):
        return jsonify({"error": "Invalid browse id"}), 400
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        return jsonify(_album_payload(client, browse_id))
    except Exception as exc:
        traceback.print_exc()
        print(f"Album page failed for browse_id={browse_id!r}: {exc}", flush=True)
        return jsonify({"error": str(exc)}), 500

@app.get("/api/playlists")
def playlists():
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        result = []
        for p in client.get_library_playlists(limit=None):
            playlist_id = clean(p.get("playlistId"))
            count = p.get("count", 0)
            if playlist_id == "LM":
                # The library shelf often reports LM with count=0; use the authoritative liked-song response.
                count = len(client.get_liked_songs(limit=None).get("tracks", []))
            result.append({"id": playlist_id, "title": clean(p.get("title", "Untitled playlist")),
                           "count": count, "thumbnail": thumbnail(p.get("thumbnails")),
                           "owned": playlist_id != "LM" and p.get("privacy") != "PUBLIC"})
        # A lapsed session makes get_library_playlists return an EMPTY list without
        # raising — indistinguishable from a genuinely empty library. Probe the
        # session before trusting an empty result, or the app silently hollows out.
        if not result and session_state() == "expired":
            cached = load_library_cache("playlists")
            if cached is not None:
                return jsonify({"cached": True, "playlists": cached})
        save_library_cache("playlists", result)
        return jsonify(result)
    except Exception as exc:
        # A lapsed session must never hard-lock the library: serve the last known
        # playlist list (the session banner already tells the user to reconnect).
        if is_auth_failure(exc):
            cached = load_library_cache("playlists")
            if cached is not None:
                return jsonify({"cached": True, "playlists": cached})
        return api_error(exc)

@app.get("/api/liked")
def liked():
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        songs = client.get_liked_songs(limit=None).get("tracks", [])
        liked_tracks = [track for item in songs if (track := track_data(item))]
        payload = {"id": "LM", "title": "Liked Music", "count": len(liked_tracks), "thumbnail": thumbnail(songs[0].get("thumbnails")) if songs else None,
                   "tracks": liked_tracks}
        # Same silent-empty trap as /api/playlists: a lapsed session can return
        # zero songs without raising. Don't let that overwrite a healthy cache.
        if not songs and session_state() == "expired":
            cached = load_library_cache("liked")
            if cached is not None:
                return jsonify({**cached, "cached": True})
        save_library_cache("liked", payload)
        return jsonify(payload)
    except Exception as exc:
        if is_auth_failure(exc):
            cached = load_library_cache("liked")
            if cached is not None:
                return jsonify({**cached, "cached": True})
        return api_error(exc)

@app.get("/api/playlist/<pid>")
def playlist(pid):
    client = get_yt()
    if client is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    if not valid_playlist_id(pid):
        return jsonify({"error": "Invalid playlist id"}), 400
    try:
        # Public playlists stay viewable even after a session lapses: retry with a
        # fresh unauthenticated client when the authenticated call fails.
        try:
            data = client.get_playlist(pid, limit=None)
        except Exception:
            if not is_auth_failure(sys.exc_info()[1]):
                raise
            from ytmusicapi import YTMusic
            client = YTMusic()
            data = client.get_playlist(pid, limit=None)
        tracks = [track for item in data.get("tracks", []) if (track := track_data(item))]
        # Record the view so /api/playlists/recent can surface it.
        try:
            with db_connection() as db:
                db.execute(
                    """INSERT INTO playlist_history (playlist_id, title, thumbnail, track_count, last_played)
                       VALUES (?, ?, ?, ?, datetime('now'))
                       ON CONFLICT(playlist_id) DO UPDATE SET title = excluded.title,
                       thumbnail = excluded.thumbnail, track_count = excluded.track_count,
                       last_played = datetime('now')""",
                    (clean(pid), clean(data.get("title", pid)),
                     thumbnail(data.get("thumbnails")) or (tracks[0].get("thumbnail") if tracks else None),
                     len(tracks)))
        except Exception as exc:
            print(f"Playlist history failed for {pid}: {exc}", flush=True)
        # Ownership requires the library call; a lapsed session just reports unowned.
        owned = pid != "LM"
        try:
            if client is get_yt():
                library_ids = {clean(item.get("playlistId")) for item in client.get_library_playlists(limit=None) if item.get("playlistId")}
                owned = clean(pid) in library_ids
        except Exception:
            owned = False
        return jsonify({"id": clean(pid), "title": clean(data.get("title", pid)),
                        "owned": owned,
                        "thumbnail": thumbnail(data.get("thumbnails")) or (tracks[0].get("thumbnail") if tracks else None),
                        "canvas": artwork(data.get("thumbnails"))["canvas"] or (tracks[0].get("canvas") if tracks else None),
                        "tracks": tracks})
    except Exception as exc:
        return api_error(exc)

# Companion video lookups are separate from stream resolution: most YouTube
# Music song IDs point at static art tracks, not official music videos. Cache
# both positive and negative answers so changing tracks does not repeatedly
# search YouTube Music during one session.
COMPANION_VIDEO_TTL = 6 * 60 * 60
companion_video_cache = {}
companion_video_cache_lock = threading.Lock()


def _normalized_search_tokens(value):
    return [token for token in re.findall(r"[a-z0-9]+", clean(value).lower())
            if token not in {"the", "a", "an", "feat", "ft", "official", "video", "music"}]


def _video_duration_seconds(item):
    for key in ("duration_seconds", "lengthSeconds", "duration", "length"):
        value = item.get(key) if isinstance(item, dict) else None
        parsed = parse_duration(value)
        if parsed is not None:
            return parsed
    return None


def _video_cache_get(audio_video_id):
    try:
        with db_connection() as db:
            row = db.execute("SELECT * FROM video_resolutions WHERE audio_video_id = ?", (audio_video_id,)).fetchone()
            return dict(row) if row else None
    except sqlite3.Error:
        return None


def _video_cache_save(audio_video_id, music_video_id, title, artist, source):
    try:
        with db_connection() as db:
            db.execute("""INSERT INTO video_resolutions(audio_video_id, music_video_id, title, artist, source)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(audio_video_id) DO UPDATE SET music_video_id=excluded.music_video_id,
                       title=excluded.title, artist=excluded.artist, source=excluded.source,
                       resolved_at=CURRENT_TIMESTAMP""",
                       (audio_video_id, music_video_id, title, artist, source))
    except sqlite3.Error:
        pass


def _companion_candidate_score(item, title, artist, audio_duration=None):
    """Score a raw YT Music video result while rejecting non-video releases."""
    video_type = clean(item.get("videoType") or item.get("type") or item.get("category") or item.get("resultType")).upper().replace("-", "_")
    if video_type not in {
        "VIDEO", "MUSIC_VIDEO", "OFFICIAL_MUSIC_VIDEO", "MUSIC_VIDEO_TYPE_ATV",
        "MUSIC_VIDEO_TYPE_OMV",
    }:
        return None
    candidate_duration = _video_duration_seconds(item)
    if audio_duration is not None and candidate_duration is not None and abs(candidate_duration - audio_duration) > 15:
        return None
    candidate_title = clean(item.get("title"))
    raw_artists = item.get("artists") or item.get("artist") or []
    if isinstance(raw_artists, list):
        candidate_artist = ", ".join(clean(value.get("name")) if isinstance(value, dict) else clean(value)
                                    for value in raw_artists)
    else:
        candidate_artist = clean(raw_artists)
    haystack = f"{candidate_title} {candidate_artist}".lower()
    blocked = ("official audio", "audio only", "lyrics", "lyric video", "visualizer",
               "karaoke", "instrumental", "cover", "live version", "live at", "type beat")
    if any(marker in haystack for marker in blocked):
        return None
    wanted_title = _normalized_search_tokens(title)
    wanted_artist = _normalized_search_tokens(artist)
    candidate_tokens = set(_normalized_search_tokens(candidate_title) + _normalized_search_tokens(candidate_artist))
    if not wanted_title or not set(wanted_title).issubset(candidate_tokens):
        return None
    title_hits = sum(token in candidate_tokens for token in wanted_title)
    artist_hits = sum(token in candidate_tokens for token in wanted_artist)
    score = title_hits * 10 + artist_hits * 3
    if "official" in haystack:
        score += 4
    if "music video" in haystack:
        score += 3
    if item.get("videoId") and valid_video_id(item.get("videoId")):
        score += 1
    return score


@app.get("/api/track-video/<video_id>")
@rate_limit("track-video", 12, 30)
def companion_video(video_id):
    """Find an official-video candidate for a YouTube Music art-track ID."""
    video_id = clean(video_id)
    title = clean(request.args.get("title"))[:200]
    artist = clean(request.args.get("artist"))[:200]
    explicit_id = clean(request.args.get("music_video_id") or request.args.get("musicVideoId"))
    audio_duration = parse_duration(request.args.get("audio_duration"))
    cache_key = (video_id, title.lower(), artist.lower(), explicit_id)
    now = time.time()
    if not valid_video_id(video_id):
        return jsonify({"has_video": False, "video_id": None})
    # An explicit companion id has already been selected by the catalog; the
    # only verification needed here is the YouTube ID shape. Never search again.
    if valid_video_id(explicit_id):
        payload = {"has_video": True, "video_id": explicit_id, "source": "explicit"}
        _video_cache_save(video_id, explicit_id, title, artist, "explicit")
        return jsonify(payload)
    cached_db = _video_cache_get(video_id)
    if cached_db is not None:
        payload = {"has_video": bool(valid_video_id(cached_db.get("music_video_id"))),
                   "video_id": cached_db.get("music_video_id") if valid_video_id(cached_db.get("music_video_id")) else None,
                   "source": cached_db.get("source", "cache")}
        return jsonify({**payload, "cached": True})
    cache_key = (video_id, title.lower(), artist.lower())
    now = time.time()
    with companion_video_cache_lock:
        expired = [key for key, item in companion_video_cache.items()
                   if now - item["timestamp"] >= COMPANION_VIDEO_TTL]
        for key in expired:
            companion_video_cache.pop(key, None)
        cached = companion_video_cache.get(cache_key)
        if cached and now - cached["timestamp"] < COMPANION_VIDEO_TTL:
            return jsonify({**cached["payload"], "cached": True})
    if not valid_video_id(video_id) or not title or not artist:
        payload = {"has_video": False, "video_id": None}
        return jsonify(payload)
    try:
        client = get_yt()
        if client is None:
            from ytmusicapi import YTMusic
            client = YTMusic()
        query = f"{artist} {title} official music video"
        try:
            results = client.search(query, filter="videos", limit=3)
        except TypeError:
            results = client.search(query, filter="videos")[:3]
        except Exception:
            # A stale authenticated session should not hide public video
            # availability; retry the same narrow search anonymously.
            from ytmusicapi import YTMusic
            public_client = YTMusic()
            try:
                results = public_client.search(query, filter="videos", limit=3)
            except TypeError:
                results = public_client.search(query, filter="videos")[:3]
        audio_duration = parse_duration(request.args.get("audio_duration"))
        ranked = []
        for item in results or []:
            if not isinstance(item, dict):
                continue
            candidate_id = clean(item.get("videoId"))
            if not valid_video_id(candidate_id) or candidate_id == video_id:
                continue
            score = _companion_candidate_score(item, title, artist, audio_duration)
            if score is not None:
                ranked.append((score, item))
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        if ranked:
            best = ranked[0][1]
            payload = {"has_video": True, "video_id": clean(best.get("videoId")),
                       "title": clean(best.get("title"))}
        else:
            payload = {"has_video": False, "video_id": None}
    except Exception as exc:
        print(f"Companion video lookup failed for {video_id}: {exc}", flush=True)
        payload = {"has_video": False, "video_id": None}
    with companion_video_cache_lock:
        companion_video_cache[cache_key] = {"payload": payload, "timestamp": time.time()}
    _video_cache_save(video_id, payload.get("video_id"), title, artist, "search" if payload["has_video"] else "negative")
    return jsonify(payload)


# Progressive video URLs are short-lived, so cache the resolver result rather
# than downloading video into the audio cache. Three hours is short enough to
# avoid serving expired URLs indefinitely and long enough for repeated toggles.
VIDEO_STREAM_TTL = 3 * 60 * 60
video_stream_cache = {}
video_stream_cache_lock = threading.Lock()

# Direct audio URLs are also short-lived and must never be shared between
# different YouTube IDs. The cache stores only resolver results, not media.
AUDIO_STREAM_TTL = 3 * 60 * 60
audio_stream_cache = {}
audio_stream_cache_lock = threading.Lock()


def _progressive_video_url(video_id):
    """Resolve one browser-playable, pre-muxed stream without runtime muxing.

    The format ladder intentionally never combines bestvideo+bestaudio: native
    HTML5 playback needs one progressive file with both codecs.  Format 22 and
    18 are kept as explicit fallbacks because they are YouTube's dependable
    muxed MP4 formats when a client does not advertise a richer progressive
    stream.  After the quality tiers the ladder relaxes to worst[ext=mp4],
    worstvideo[ext=mp4], worst[ext=webm], then bare worst so a video whose
    only progressive option is WebM still resolves instead of failing.
    """
    import yt_dlp
    attempts = [
        {"extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
         "http_headers": None},
        {"extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
         "http_headers": auth_headers() or None},
    ]
    last_error = None
    for attempt in attempts:
        options = {
            # Never add a DASH pair here: that would require runtime muxing and
            # makes the browser wait for a second stream before it can render.
            "format": "best[ext=mp4][protocol^=http][acodec!=none][vcodec!=none][height<=1080]/22/18/worst[ext=mp4]/worstvideo[ext=mp4]/worst[ext=webm]/worst",
            "format_sort": ["res:1080", "fps:30", "br"],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 15,
            "http_headers": attempt["http_headers"],
            "extractor_args": attempt["extractor_args"],
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            url = info.get("url")
            if url and info.get("vcodec") not in (None, "none") and info.get("acodec") not in (None, "none"):
                return url, info.get("title")
            last_error = RuntimeError("No progressive video stream is available for this track")
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("No progressive video stream is available for this track")


def _resolve_video_payload(video_id):
    """Resolve/cache a progressive URL; shared by the current and legacy APIs."""
    video_id = clean(video_id)
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id", "url": None, "stream_url": None}), 400
    now = time.time()
    with video_stream_cache_lock:
        # Keep this process cache bounded if a long session watches many videos.
        expired = [key for key, item in video_stream_cache.items() if now - item["timestamp"] >= VIDEO_STREAM_TTL]
        for key in expired:
            video_stream_cache.pop(key, None)
        cached = video_stream_cache.get(video_id)
        if cached and now - cached["timestamp"] < VIDEO_STREAM_TTL:
            return jsonify({"url": cached["url"], "stream_url": cached["url"],
                            "title": cached.get("title"), "cached": True})
        if cached:
            video_stream_cache.pop(video_id, None)
    try:
        url, title = _progressive_video_url(video_id)
        with video_stream_cache_lock:
            video_stream_cache[video_id] = {"url": url, "title": title, "timestamp": time.time()}
        return jsonify({"url": url, "stream_url": url, "title": title, "cached": False})
    except Exception as exc:
        print(f"Progressive video resolver failed for {video_id}: {exc}", flush=True)
        return jsonify({"error": str(exc), "url": None, "stream_url": None}), 502


@app.get("/api/video-url/<video_id>")
@rate_limit("video-url", 6, 15)
def video_url(video_id):
    """Return a cached muxed MP4 URL for native Theatre playback."""
    return _resolve_video_payload(video_id)


@app.get("/api/video-stream/<video_id>")
@rate_limit("video-stream", 6, 15)
def video_stream(video_id):
    """Compatibility route for clients using the original resolver path."""
    return _resolve_video_payload(video_id)


@app.get("/api/stream-video/<video_id>")
def stream_video_legacy(video_id):
    """Compatibility alias for older Theatre clients."""
    response = video_stream(video_id)
    if isinstance(response, tuple):
        return response
    payload = response.get_json() or {}
    return jsonify({"video_url": payload.get("url"), "cached": payload.get("cached", False)}), response.status_code

@app.get("/api/stream-cache/<video_id>")
def stream_cache(video_id):
    """Serve a cached audio file with HTTP range support for seeking."""
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400
    path = cached_audio(video_id)
    if path is None:
        return jsonify({"error": "Not cached yet", "url": None}), 404
    response = send_file(path, conditional=True)
    response.headers["Accept-Ranges"] = "bytes"
    return response

def _is_media_url(url):
    """A playable stream URL: never a storyboard/thumbnail image."""
    u = str(url or "")
    if not u or ("http://" not in u and "https://" not in u):
        return False
    return all(token not in u for token in ("storyboard", ".jpg", ".jpeg", ".webp", ".png"))


def pick_stream_url(info):
    """Return the best standalone audio URL from an extraction result.

    Priority: highest-bitrate standalone audio (acodec != none, vcodec == none)
    -> any audio-capable format -> info["url"] -> any URL-bearing format.
    Storyboard/thumbnail URLs are rejected outright so a failed extraction can
    never masquerade as a successful stream (that caused silent "Track
    unavailable" playback failures). Standalone streams need no ffmpeg merging.
    """
    formats = info.get("formats") or []
    standalone = [f for f in formats
                  if _is_media_url(f.get("url"))
                  and f.get("acodec") not in (None, "none")
                  and f.get("vcodec") in (None, "none")]
    if standalone:
        standalone.sort(key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)
        return standalone[0].get("url")
    audio = [f for f in formats
             if _is_media_url(f.get("url")) and f.get("acodec") not in (None, "none")]
    if audio:
        audio.sort(key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)
        return audio[0].get("url")
    if _is_media_url(info.get("url")):
        return info["url"]
    any_url = [f for f in formats if _is_media_url(f.get("url"))]
    if any_url:
        any_url.sort(key=lambda f: f.get("tbr") or 0, reverse=True)
        return any_url[0].get("url")
    return None


def resolve_stream_url(video_id, quality="high"):
    """Resolve the best standalone audio URL for a video via the retry ladder.

    Returns (url, title). Crucially, cookies are NOT sent on the first passes:
    passing the browser Cookie header makes some extractions return
    storyboard-only formats (sb0-sb3) with no audio, which previously caused
    silent "Track unavailable" playback failures. Cookies are only used as a
    last-resort retry for age-gated content that needs them.
    """
    if quality not in QUALITY_FORMATS:
        quality = "high"
    import yt_dlp
    attempts = [
        {"format": QUALITY_FORMATS[quality],
         "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
         "headers": None},
        {"format": "ba/b/bestaudio/best",
         "extractor_args": {"youtube": {"player_client": ["mweb", "ios", "android", "web"]}},
         "headers": None},
        {"format": QUALITY_FORMATS[quality],
         "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
         "headers": auth_headers() or None},
        {"format": "ba/b/bestaudio/best",
         "extractor_args": {"youtube": {"player_client": ["mweb", "ios", "android", "web"]}},
         "headers": auth_headers() or None},
    ]
    for index, opts in enumerate(attempts, start=1):
        try:
            ydl_opts = {
                "format": opts["format"],
                "ignore_no_formats_error": True,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "js_engine": "node",
                "http_headers": opts["headers"],
                "extractor_args": opts["extractor_args"],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            url = pick_stream_url(info)
            if url:
                return url, info.get("title")
            print(f"No playable format for {video_id} on pass {index}", flush=True)
        except Exception as exc:
            print(f"Stream pass {index} failed for {video_id}: {exc}", flush=True)
            continue
    return None, None


def _iter_remote(remote):
    """Stream an upstream response body in chunks, closing it when done."""
    try:
        while True:
            chunk = remote.read(64 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        remote.close()


def resolve_canonical_source(track_id):
    """Resolve a canonical id to its preferred playable source."""
    if valid_canonical_id(track_id):
        with db_connection() as db:
            canonical = db.execute(
                "SELECT preferred_source FROM canonical_tracks WHERE id = ?", (track_id,)
            ).fetchone()
            if canonical:
                source = canonical["preferred_source"]
                source_row = db.execute(
                    """SELECT source, source_id, stream_url FROM track_sources
                       WHERE canonical_id = ? ORDER BY (source = ?) DESC, id ASC LIMIT 1""",
                    (track_id, source),
                ).fetchone()
                if source_row:
                    return dict(source_row)
        return None
    if valid_video_id(track_id):
        return {"source": "youtube", "source_id": track_id, "stream_url": None}
    return None


def source_stream_url(source, source_id, cached_url=None):
    """Resolve a provider source into a browser-playable URL."""
    if cached_url:
        return cached_url
    if source == "soundcloud":
        return SoundCloudProvider().get_stream_url(source_id)
    if source == "youtube":
        url, _ = resolve_stream_url(source_id, SETTINGS.get("quality", "high"))
        return url
    return None


@app.get("/api/stream/<track_id>")
@rate_limit("stream", 8, 20)
def stream(track_id):
    resolved = resolve_canonical_source(clean(track_id))
    if not resolved:
        return jsonify({"error": "Invalid or unknown track id", "url": None}), 400
    source, source_id = resolved["source"], resolved["source_id"]
    print(f"Resolving {source} stream for track_id: {track_id} (source_id={source_id})", flush=True)
    # Existing local audio cache is keyed by the YouTube source id.
    cached = cached_audio(source_id) if source == "youtube" else None
    if cached is not None:
        print(f"Stream served from cache: {cached.name}", flush=True)
        return jsonify({"url": f"/api/stream-cache/{source_id}", "cached": True, "title": None,
                        "source": source, "source_id": source_id, "video_id": source_id})
    track_id = clean(track_id)
    quality = request.args.get("quality") or SETTINGS.get("quality", "high")
    try:
        stream_url = None
        title = None
        if source == "youtube":
            now = time.time()
            with audio_stream_cache_lock:
                cached_result = audio_stream_cache.get(source_id)
                if cached_result and now - cached_result["timestamp"] < AUDIO_STREAM_TTL:
                    stream_url = cached_result["url"]
                    title = cached_result.get("title")
            if not stream_url:
                stream_url, title = resolve_stream_url(source_id, quality)
                if stream_url:
                    with audio_stream_cache_lock:
                        audio_stream_cache[source_id] = {"url": stream_url, "title": title, "timestamp": time.time()}
        else:
            stream_url = source_stream_url(source, source_id, resolved.get("stream_url"))
        if not stream_url:
            raise RuntimeError("yt-dlp returned no playable format")
        # Only YouTube audio participates in the existing local download cache;
        # SoundCloud URLs are short-lived and are resolved on demand.
        if source == "youtube":
            download_to_cache(source_id, auth_headers())
        # Return a same-origin proxy URL instead of the raw provider URL:
        # cross-origin googlevideo media is CORS-silenced in the Web Audio
        # analyser (Theatre Mode visualizer showed no bars on direct streams),
        # and proxy URLs are also stable per video for the gapless preload.
        proxy_path = f"/api/proxy/{source_id}" if source == "youtube" else f"/api/proxy-source/{source}/{urllib.parse.quote(source_id, safe='') }"
        return jsonify({"url": proxy_path, "cached": False, "title": title,
                        "source": source, "source_id": source_id, "video_id": source_id,
                        "canonical_id": track_id if valid_canonical_id(track_id) else None})
    except Exception as exc:
        traceback.print_exc()
        print(f"Stream resolver failed for track_id={track_id}: {exc}", flush=True)
        return jsonify({"error": str(exc), "url": None}), 500


@app.get("/api/proxy-source/<source>/<source_id>")
@rate_limit("proxy-source", 8, 20)
def proxy_source_stream(source, source_id):
    """Proxy a non-YouTube provider stream with Range support."""
    if source != "soundcloud" or not source_id or len(source_id) > 80:
        return jsonify({"error": "Invalid provider source"}), 400
    try:
        stream_url = source_stream_url(source, source_id)
        if not stream_url:
            raise RuntimeError("Provider returned no playable stream")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        if request.headers.get("Range"):
            headers["Range"] = request.headers["Range"]
        remote = urllib.request.urlopen(urllib.request.Request(stream_url, headers=headers), timeout=30)
        response = Response(stream_with_context(_iter_remote(remote)),
                            status=206 if request.headers.get("Range") else 200,
                            content_type=remote.headers.get_content_type() or "audio/mpeg")
        response.headers["Accept-Ranges"] = "bytes"
        for header in ("Content-Range", "Content-Length"):
            if remote.headers.get(header):
                response.headers[header] = remote.headers[header]
        return response
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.get("/api/proxy/<video_id>")
@rate_limit("proxy", 8, 20)
def proxy_stream(video_id):
    """Same-origin audio proxy with HTTP Range support.

    Serves cached audio directly; otherwise resolves the standalone stream and
    relays the bytes so the browser treats playback as same-origin (required
    for the Theatre Mode visualizer's Web Audio analyser) while still
    supporting seeking via Range requests.
    """
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400
    video_id = clean(video_id)
    cached = cached_audio(video_id)
    if cached is not None:
        response = send_file(cached, conditional=True)
        response.headers["Accept-Ranges"] = "bytes"
        return response
    quality = request.args.get("quality") or SETTINGS.get("quality", "high")
    try:
        stream_url, _ = resolve_stream_url(video_id, quality)
        if not stream_url:
            raise RuntimeError("yt-dlp returned no playable format")
    except Exception as exc:
        traceback.print_exc()
        print(f"Proxy resolution failed for video_id={video_id}: {exc}", flush=True)
        return jsonify({"error": str(exc)}), 500
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header
    remote = None
    try:
        upstream = urllib.request.Request(stream_url, headers=headers)
        remote = urllib.request.urlopen(upstream, timeout=30)
        response = Response(
            stream_with_context(_iter_remote(remote)),
            status=206 if range_header else 200,
            content_type=remote.headers.get_content_type() or "audio/mpeg",
        )
        response.headers["Accept-Ranges"] = "bytes"
        if remote.headers.get("Content-Range"):
            response.headers["Content-Range"] = remote.headers["Content-Range"]
        if remote.headers.get("Content-Length"):
            response.headers["Content-Length"] = remote.headers["Content-Length"]
        return response
    except Exception as exc:
        if remote is not None:
            try:
                remote.close()
            except Exception:
                pass
        traceback.print_exc()
        print(f"Proxy stream failed for video_id={video_id}: {exc}", flush=True)
        return jsonify({"error": str(exc)}), 502

if __name__ == "__main__":
    # LAN/VPN remote mode is opt-in. Keep localhost as the safe default because
    # this process holds the user's Google session cookies. For an iPhone on a
    # trusted home LAN, set YTM_BIND_HOST=0.0.0.0 and optionally restrict
    # YTM_CORS_ORIGINS to the exact frontend origin.
    host = os.getenv("YTM_BIND_HOST", "127.0.0.1")
    app.run(host=host, port=int(os.getenv("YTM_BACKEND_PORT", "5178")), debug=False)
