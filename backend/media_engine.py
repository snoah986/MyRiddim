"""Artist and track backdrop media for Theatre Mode.

The Flask request only performs provider metadata lookup and cache inspection.
The yt-dlp extraction is dispatched to a daemon worker so cutting a loop never
blocks the API response or the main Flask thread.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, jsonify, request, send_from_directory


media_engine_bp = Blueprint("media_engine", __name__)
LOOP_DIR = Path(__file__).resolve().parent / "cache" / "loops"
LOOP_DIR.mkdir(parents=True, exist_ok=True)

_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]+")
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_LOOP_JOBS: set[str] = set()
_LOOP_JOBS_LOCK = threading.Lock()
_LOOP_JOB_SLOTS = threading.BoundedSemaphore(value=2)


def _safe_cache_key(value: str | None) -> str:
    """Turn a track or artist id into a safe, stable cache filename."""
    return _SAFE_ID.sub("_", str(value or "").strip())[:160]


def _loop_url(cache_key: str) -> str:
    return f"/media/loops/{quote(cache_key, safe='_-')}.mp4"


def _thumbnail_url(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("url")
    return None


def _artist_backdrop(artist):
    """Select the largest wide artist thumbnail with at least 1280px width."""
    thumbnails = artist.get("thumbnails") if isinstance(artist, dict) else None
    if not isinstance(thumbnails, list):
        return None
    candidates = []
    for item in thumbnails:
        if not isinstance(item, dict):
            continue
        url = _thumbnail_url(item)
        try:
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if url and width >= 1280 and (not height or width >= height * 1.35):
            candidates.append((width * max(height, 1), width, url))
    return max(candidates, default=(0, 0, None))[2]


def _upgrade_artist_image(url):
    """Remove YouTube Music thumbnail size limits for a high-res fallback."""
    if not url:
        return None
    value = str(url)
    value = re.sub(r"=w\d+-h\d+", "=s3840", value)
    value = re.sub(r"=s\d+", "=s3840", value)
    return value


def _track_image(track_id):
    if _YOUTUBE_ID.fullmatch(str(track_id or "")):
        return f"https://i.ytimg.com/vi/{track_id}/maxresdefault.jpg"
    return None


def _get_provider():
    """Resolve the app's singleton provider lazily to avoid import cycles."""
    try:
        from .app import get_yt
    except ImportError:
        from app import get_yt
    return get_yt()


def _find_downloaded_file(prefix: Path) -> Path | None:
    files = [path for path in prefix.parent.glob(f"{prefix.name}.*") if path.is_file()]
    return max(files, key=lambda path: path.stat().st_mtime_ns, default=None)


def _generate_loop(track_id: str, cache_key: str, artist_name: str) -> None:
    """Download a short video-only MP4 for a track in a background worker."""
    if not cache_key:
        return
    final_path = LOOP_DIR / f"{cache_key}.mp4"
    if final_path.is_file() and final_path.stat().st_size > 0:
        return

    temp_prefix = LOOP_DIR / f".{cache_key}.download"
    try:
        yt_dlp = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        if not yt_dlp:
            print("[MediaEngine] yt-dlp not found in PATH", flush=True)
            return
        for old in LOOP_DIR.glob(f"{temp_prefix.name}.*"):
            try:
                old.unlink()
            except OSError:
                pass

        if _YOUTUBE_ID.fullmatch(track_id or ""):
            target = f"https://www.youtube.com/watch?v={track_id}"
        else:
            target = f"ytsearch1:{artist_name} official music video"
        command = [
            yt_dlp,
            "--downloader", "ffmpeg",
            "--downloader-args", "ffmpeg_i:-ss 00:06 -to 00:14",
            "-f", "bestvideo[height<=1080][ext=mp4]/bestvideo[height<=720]",
            "-o", f"{temp_prefix}.%(ext)s",
            "--quiet",
            "--no-warnings",
            "--no-playlist",
            "--merge-output-format", "mp4",
            "--",
            target,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            print("[MediaEngine] yt-dlp not found in PATH", flush=True)
            return
        if result.returncode != 0:
            print(f"[MediaEngine] loop extraction failed for {cache_key}: {result.stderr.strip()}", flush=True)
            return

        source = _find_downloaded_file(temp_prefix)
        if not source:
            print(f"[MediaEngine] yt-dlp produced no loop for {cache_key}", flush=True)
            return

        ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if not ffmpeg:
            print("[MediaEngine] ffmpeg not found in PATH", flush=True)
            if source.suffix.lower() == ".mp4":
                os.replace(str(source), str(final_path))
            return

        stripped = LOOP_DIR / f".{cache_key}.stripped.mp4"
        try:
            strip_result = subprocess.run([
                ffmpeg, "-y", "-i", str(source),
                "-map", "0:v:0", "-an", "-c:v", "copy",
                "-movflags", "+faststart", str(stripped),
            ], capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            print("[MediaEngine] ffmpeg not found in PATH", flush=True)
            return
        if strip_result.returncode != 0 or not stripped.is_file() or stripped.stat().st_size == 0:
            print(f"[MediaEngine] ffmpeg post-process failed for {cache_key}: {strip_result.stderr.strip()}", flush=True)
            return
        os.replace(str(stripped), str(final_path))
    except subprocess.TimeoutExpired:
        print(f"[MediaEngine] loop extraction timed out for {cache_key}", flush=True)
    except OSError as exc:
        print(f"[MediaEngine] loop unavailable for {cache_key}: {exc}", flush=True)
    finally:
        for old in LOOP_DIR.glob(f".{cache_key}.*"):
            try:
                old.unlink()
            except OSError:
                pass
        with _LOOP_JOBS_LOCK:
            _LOOP_JOBS.discard(cache_key)
        _LOOP_JOB_SLOTS.release()


def _start_loop_job(track_id: str, cache_key: str, artist_name: str) -> None:
    if not _LOOP_JOB_SLOTS.acquire(blocking=False):
        return
    with _LOOP_JOBS_LOCK:
        if cache_key in _LOOP_JOBS:
            _LOOP_JOB_SLOTS.release()
            return
        _LOOP_JOBS.add(cache_key)
    try:
        threading.Thread(
            target=_generate_loop,
            args=(track_id, cache_key, artist_name),
            name=f"theatre-loop-{cache_key}",
            daemon=True,
        ).start()
    except Exception:
        with _LOOP_JOBS_LOCK:
            _LOOP_JOBS.discard(cache_key)
        _LOOP_JOB_SLOTS.release()


def get_media_backdrop(track_id=None, artist_id=None, title="", artist=""):
    """Return media immediately and queue a missing direct-track loop."""
    track_id = str(track_id or "").strip()
    artist_id = str(artist_id or "").strip()
    artist_name = str(artist or "").strip()
    cache_key = _safe_cache_key(track_id or artist_id)
    if not cache_key:
        return {"loopUrl": None, "backdropUrl": None}

    artist_image = None
    if artist_id:
        try:
            provider = _get_provider()
            if provider is not None:
                artist_image = _artist_backdrop(provider.get_artist(artist_id))
        except Exception as exc:
            print(f"[MediaEngine] artist backdrop lookup failed for {artist_id}: {exc}", flush=True)

    cached = LOOP_DIR / f"{cache_key}.mp4"
    loop_url = _loop_url(cache_key) if cached.is_file() and cached.stat().st_size > 0 else None
    if loop_url is None:
        _start_loop_job(track_id, cache_key, artist_name)

    # Track artwork is the most reliable high-resolution image while the loop
    # is being generated. The provider banner is the next-best fallback.
    backdrop_url = _track_image(track_id) or _upgrade_artist_image(artist_image)
    return {"loopUrl": loop_url, "backdropUrl": backdrop_url}


@media_engine_bp.get("/api/media/prepare")
def media_prepare():
    """Warm a direct track loop without requiring Theatre Mode to be open."""
    track_id = str(request.args.get("videoId") or request.args.get("video_id") or "").strip()
    if not _YOUTUBE_ID.fullmatch(track_id):
        return jsonify({"ready": False, "error": "Invalid YouTube video id"}), 400
    media = get_media_backdrop(track_id=track_id)
    return jsonify({"ready": bool(media.get("loopUrl")), **media})


@media_engine_bp.get("/api/media/backdrop")
def media_backdrop():
    track_id = request.args.get("trackId") or request.args.get("track_id")
    artist_id = request.args.get("artistId") or request.args.get("artist_id")
    title = request.args.get("title") or ""
    artist = request.args.get("artistName") or request.args.get("artist_name") or ""
    return jsonify(get_media_backdrop(track_id, artist_id, title, artist))


@media_engine_bp.get("/media/loops/<path:filename>")
def media_loop(filename):
    """Serve only generated MP4 loop assets with the correct MIME type."""
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith(".mp4"):
        return jsonify({"error": "Invalid loop filename"}), 400
    return send_from_directory(LOOP_DIR, safe_name, mimetype="video/mp4", conditional=True)
