"""Local YouTube Music API bridge."""
from pathlib import Path
import json
import os
import tempfile
import sqlite3
import re
import threading
import time
import traceback
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, jsonify, request, send_file, Response, stream_with_context
from flask_cors import CORS

app = Flask(__name__)
# The app holds the user's real Google session cookies, so only the local
# frontend/backend origins may read responses. A wildcard here would let any
# website loaded in the browser silently read localhost API responses.
CORS(app, origins=[
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5178", "http://127.0.0.1:5178",
])
ROOT = Path(__file__).resolve().parent.parent
AUTH_PATH = ROOT / "browser.json"
AUTH_CANDIDATES = [AUTH_PATH, Path(__file__).parent / "browser.json", ROOT / "oauth.json"]
STATS_PATH = Path(__file__).parent / "stats.db"
CACHE_DIR = ROOT / ".freebuff" / "audio_cache"
CACHE_LIMIT_BYTES = 1024 ** 3  # 1 GB default LRU ceiling
SETTINGS_PATH = Path(__file__).parent / "settings.json"
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
PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def valid_video_id(value):
    """YouTube video IDs are exactly 11 chars from [A-Za-z0-9_-]."""
    return bool(value) and bool(VIDEO_ID_RE.match(str(value)))


def valid_playlist_id(value):
    """Playlist/browse IDs are short base64url-ish strings (PL..., LM, WL...)."""
    return bool(value) and bool(PLAYLIST_ID_RE.match(str(value)))


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
    """Current cache statistics: file count and total bytes."""
    files = [p for p in CACHE_DIR.iterdir() if p.is_file()] if CACHE_DIR.is_dir() else []
    return {"count": len(files), "size_bytes": sum(p.stat().st_size for p in files)}

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
        except Exception as exc:
            print(f"Cache download failed for {vid}: {exc}", flush=True)
        finally:
            with _cache_inflight_lock:
                _cache_inflight.discard(vid)
    threading.Thread(target=worker, daemon=True).start()


def db_connection():
    connection = sqlite3.connect(STATS_PATH)
    connection.row_factory = sqlite3.Row
    return connection


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
            listen_duration_seconds INTEGER NOT NULL
        )""")

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
try:
    yt = make_yt()
    AUTHENTICATED = find_auth_file() is not None
except Exception as exc:
    yt, AUTHENTICATED, STARTUP_ERROR = None, False, str(exc)

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

def search_item(item):
    kind = item.get("resultType", "song")
    artists = item.get("artists") or []
    artist_names = ", ".join(clean(a.get("name")) for a in artists if isinstance(a, dict))
    artist_name = artist_names or clean(item.get("artist"))
    album = item.get("album")
    album_name = clean(album.get("name")) if isinstance(album, dict) else clean(album)
    video_id = clean(item.get("videoId"))
    value = {"id": video_id if kind == "song" else clean(item.get("browseId") or item.get("playlistId")),
             "type": kind, "title": clean(item.get("title")), "artist": artist_name,
             "album": album_name, "thumbnail": thumbnail(item.get("thumbnails"))}
    if kind == "song":
        value["videoId"] = video_id
        value["duration"] = clean(item.get("duration"))
    return value

@app.get("/api/search")
@rate_limit("search", 8, 10)
def search():
    if yt is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    query = clean(request.args.get("q"))[:120]
    allowed = {"songs": "songs", "albums": "albums", "artists": "artists", "playlists": "playlists"}
    filter_name = allowed.get(clean(request.args.get("filter")).lower())
    if not query:
        return jsonify({"query": "", "results": []})
    try:
        results = yt.search(query, filter=filter_name) if filter_name else yt.search(query)
        return jsonify({"query": query, "results": [search_item(item) for item in results]})
    except Exception as exc:
        traceback.print_exc()
        print(f"Search failed for query={query!r}: {exc}", flush=True)
        return jsonify({"error": str(exc), "results": []}), 500


def require_yt():
    if yt is None or not AUTHENTICATED:
        raise RuntimeError("An authenticated YouTube Music session is required")
    return yt

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

def clean(value):
    """Normalize metadata from YouTube's inconsistent text fields."""
    return " ".join(str(value or "").replace("\\n", " ").replace("\\r", " ").replace("\\t", " ").split()).strip()

def track_data(track):
    artists = ", ".join(clean(a.get("name")) for a in track.get("artists", []) if a.get("name"))
    return {
        "videoId": clean(track.get("videoId")),
        "title": clean(track.get("title")) or "Unknown title",
        "artist": clean(artists),
        "album": clean((track.get("album") or {}).get("name")),
        "duration": clean(track.get("duration")),
        "thumbnail": artwork(track.get("thumbnails") or track.get("thumbnail"))["thumbnail"],
        "canvas": artwork(track.get("thumbnails") or track.get("thumbnail"))["canvas"],
    }

def session_state():
    """Probe the live session's entitlement with one lightweight liked-song call.

    When browser.json credentials lapse, YouTube serves the logged-out liked
    page ("Looking for what you've liked?") and ytmusicapi raises a parse
    error — the earliest reliable signal that the session needs re-auth.
    """
    if yt is None or not AUTHENTICATED:
        return "unauthenticated"
    try:
        yt.get_liked_songs(limit=1)
        return "ok"
    except Exception:
        return "expired"


@app.get("/api/health")
def health():
    session = session_state()
    # A lapsed session is reported honestly: status flips to "expired" and
    # authenticated drops to false so consumers never trust a dead session.
    return jsonify({"status": "expired" if session == "expired" else "ok",
                    "port": 5178, "backend": "ytm-player",
                    "ytmusic": yt is not None,
                    "authenticated": AUTHENTICATED and session != "expired",
                    "session": session})


@app.post("/api/auth/logout")
def auth_logout():
    """Forget the stored credentials and drop the live client."""
    global yt, AUTHENTICATED, STARTUP_ERROR
    for path in (AUTH_PATH, Path(__file__).parent / "browser.json"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    yt = None
    AUTHENTICATED = False
    STARTUP_ERROR = None
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


@app.post("/api/auth/setup")
def auth_setup():
    """Validate and atomically persist pasted ytmusicapi browser.json data."""
    global yt, AUTHENTICATED, STARTUP_ERROR
    body = request.get_json(silent=True) or {}
    raw = body.get("auth") or body.get("headers") or body.get("config")
    if not isinstance(raw, str) or not raw.strip():
        return api_error(ValueError("Paste the contents of browser.json or raw request headers."), 400)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, (dict, list)):
            raise ValueError("Authentication JSON must be an object or array.")
    except json.JSONDecodeError:
        # ytmusicapi accepts raw copied request headers as well.
        parsed = None

    temp_name = None
    try:
        if parsed is not None:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=ROOT, encoding="utf-8") as temp:
                json.dump(parsed, temp, indent=2)
                temp_name = temp.name
            candidate = make_yt(Path(temp_name))
        else:
            from ytmusicapi import YTMusic
            raw_temp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=ROOT)
            raw_temp.close()
            temp_name = raw_temp.name
            YTMusic.setup(filepath=temp_name, headers_raw=raw)
            candidate = make_yt(Path(temp_name))
        # A lightweight authenticated call validates the credential before replacing it.
        candidate.get_library_playlists(limit=1)
        if temp_name:
            os.replace(temp_name, AUTH_PATH)
        yt = make_yt(AUTH_PATH)
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
    title, artist = clean(request.args.get("title"))[:200], clean(request.args.get("artist"))[:200]
    track_id = clean(request.args.get("track_id"))
    if track_id and not valid_video_id(track_id):
        track_id = None
    try:
        plain = ""
        # 1. LRCLIB is the preferred source for time-synced lyrics: query artist,
        #    title, and duration so the best matching record wins.
        params = urllib.parse.urlencode({"track_name": title, "artist_name": artist, "duration": clean(request.args.get("duration"))})
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
        if yt is not None and track_id:
            try:
                watch = yt.get_watch_playlist(videoId=track_id, limit=1)
                lyrics_id = watch.get("lyrics", {}).get("browseId") if isinstance(watch.get("lyrics"), dict) else watch.get("lyrics")
                if lyrics_id and hasattr(yt, "get_lyrics"):
                    result = yt.get_lyrics(lyrics_id) or {}
                    plain = plain or str(result.get("lyrics") or "").strip()
                    parsed = parse_lrc(result.get("lyrics", ""))
                    if parsed:
                        return jsonify({"synced": True, "lines": parsed})
            except Exception:
                pass
        return jsonify({"synced": False, "text": plain, "lines": []})
    except Exception:
        return jsonify({"synced": False, "text": plain, "lines": []})

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
    with db_connection() as db:
        db.execute("""INSERT INTO listens
            (video_id, title, artist, album, thumbnail_url, played_at_timestamp, listen_duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (
                clean(body.get("video_id")), clean(body.get("title")), clean(body.get("artist")),
                clean(body.get("album")), body.get("thumbnail_url"), datetime.now(timezone.utc).isoformat(), duration))
    return jsonify({"ok": True}), 201


def stat_track(row):
    return {"videoId": row["video_id"], "title": row["title"], "artist": row["artist"],
            "album": row["album"], "thumbnail": row["thumbnail_url"]}

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
    return jsonify({"month": month, "totalMinutes": round(total / 60), "monthly": [dict(stat_track(row), plays=row["plays"]) for row in rows],
                    "heavyRotation": [dict(stat_track(row), plays=row["plays"]) for row in all_time]})

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
    if yt is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        shelves = yt.get_home() or []
        tracks = []
        for shelf in shelves:
            title = clean(shelf.get("title"))
            for item in shelf.get("contents", []):
                if item.get("videoId") and ("quick" in title.lower() or not tracks):
                    tracks.append(track_data(item))
                if len(tracks) >= 12:
                    break
            if len(tracks) >= 12:
                break
        return jsonify({"title": "Quick Picks", "tracks": tracks})
    except Exception as exc:
        return api_error(exc)

@app.get("/api/playlists")
def playlists():
    if yt is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        result = []
        for p in yt.get_library_playlists(limit=None):
            playlist_id = clean(p.get("playlistId"))
            count = p.get("count", 0)
            if playlist_id == "LM":
                # The library shelf often reports LM with count=0; use the authoritative liked-song response.
                count = len(yt.get_liked_songs(limit=None).get("tracks", []))
            result.append({"id": playlist_id, "title": clean(p.get("title", "Untitled playlist")),
                           "count": count, "thumbnail": thumbnail(p.get("thumbnails")),
                           "owned": playlist_id != "LM" and p.get("privacy") != "PUBLIC"})
        return jsonify(result)
    except Exception as exc:
        return api_error(exc)

@app.get("/api/liked")
def liked():
    if yt is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    try:
        songs = yt.get_liked_songs(limit=None).get("tracks", [])
        return jsonify({"id": "LM", "title": "Liked Music", "count": len(songs), "thumbnail": thumbnail(songs[0].get("thumbnails")) if songs else None,
                        "tracks": [track_data(track) for track in songs]})
    except Exception as exc:
        return api_error(exc)

@app.get("/api/playlist/<pid>")
def playlist(pid):
    if yt is None:
        return api_error(RuntimeError("ytmusicapi is not available"))
    if not valid_playlist_id(pid):
        return jsonify({"error": "Invalid playlist id"}), 400
    try:
        data = yt.get_playlist(pid, limit=None)
        tracks = [track_data(track) for track in data.get("tracks", []) if track.get("videoId")]
        # Ownership is determined by whether this playlist is in the user's own library,
        # not by the privacy field (public user playlists would otherwise appear unowned).
        library_ids = {clean(item.get("playlistId")) for item in yt.get_library_playlists(limit=None) if item.get("playlistId")}
        return jsonify({"id": clean(pid), "title": clean(data.get("title", pid)),
                        "owned": pid != "LM" and clean(pid) in library_ids,
                        "thumbnail": thumbnail(data.get("thumbnails")) or (tracks[0].get("thumbnail") if tracks else None),
                        "canvas": artwork(data.get("thumbnails"))["canvas"] or (tracks[0].get("canvas") if tracks else None),
                        "tracks": tracks})
    except Exception as exc:
        return api_error(exc)

@app.get("/api/stream-video/<video_id>")
@rate_limit("video", 6, 15)
def stream_video(video_id):
    """Resolve a small video-only MP4 for Theatre Mode ambient visuals."""
    if not valid_video_id(video_id):
        return jsonify({"video_url": None}), 400
    try:
        import yt_dlp
        options = {
            # Prefer progressive format 18 (MP4, plays everywhere), then any MP4/WebM
            # browser-compatible progressive stream. Avoids WebM VP9-only video-only
            # formats that browsers cannot play directly.
            "format": "18/worst[ext=mp4]/worstvideo[ext=mp4]/worst[ext=webm]/worst",
            "quiet": True, "no_warnings": True, "noplaylist": True,
            "http_headers": auth_headers(),
            "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(f"https://www.youtube.com/watch?v={clean(video_id)}", download=False)
        return jsonify({"video_url": info.get("url") or None})
    except Exception:
        # Video is an enhancement; static artwork should remain usable.
        return jsonify({"video_url": None})

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


@app.get("/api/stream/<video_id>")
@rate_limit("stream", 8, 20)
def stream(video_id):
    if not valid_video_id(video_id):
        return jsonify({"error": "Invalid video id", "url": None}), 400
    print(f"Resolving stream for video_id: {video_id}", flush=True)
    # Cache-first: if we already saved audio for this track, serve it locally.
    cached = cached_audio(video_id)
    if cached is not None:
        print(f"Stream served from cache: {cached.name}", flush=True)
        return jsonify({"url": f"/api/stream-cache/{video_id}", "cached": True, "title": None})
    video_id = clean(video_id)
    quality = request.args.get("quality") or SETTINGS.get("quality", "high")
    try:
        stream_url, title = resolve_stream_url(video_id, quality)
        if not stream_url:
            raise RuntimeError("yt-dlp returned no playable format")
        # Kick off an async background download so the next play comes from cache.
        download_to_cache(video_id, auth_headers())
        # Return a same-origin proxy URL instead of the raw googlevideo URL:
        # cross-origin googlevideo media is CORS-silenced in the Web Audio
        # analyser (Theatre Mode visualizer showed no bars on direct streams),
        # and proxy URLs are also stable per video for the gapless preload.
        return jsonify({"url": f"/api/proxy/{video_id}", "cached": False, "title": title})
    except Exception as exc:
        traceback.print_exc()
        print(f"Stream resolver failed for video_id={video_id}: {exc}", flush=True)
        return jsonify({"error": str(exc), "url": None}), 500


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
    # Localhost only: this server holds the user's Google session cookies and
    # must never be reachable from the local network (e.g. cafe Wi-Fi).
    app.run(host="127.0.0.1", port=int(os.getenv("YTM_BACKEND_PORT", "5178")), debug=False)
