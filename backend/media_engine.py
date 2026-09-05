"""Artist backdrop and short video-loop services for Theatre Mode.

The request path only performs the lightweight artist lookup and checks the
local cache. yt-dlp and ffmpeg work is dispatched to daemon threads so a slow
or unavailable media tool cannot block Flask's request worker.
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
_LOOP_JOBS: set[str] = set()
_LOOP_JOBS_LOCK = threading.Lock()


def _safe_artist_id(value: str | None) -> str:
    """Make a provider id safe for a cache filename."""
    return _SAFE_ID.sub("_", str(value or "").strip())[:160]


def _loop_url(artist_id: str) -> str:
    return f"/media/loops/{quote(artist_id, safe='_-')}"


def _thumbnail_url(thumbnail):
    if isinstance(thumbnail, str):
        return thumbnail
    if isinstance(thumbnail, dict):
        return thumbnail.get("url")
    return None


def _artist_backdrop(artist):
    """Select the largest genuinely wide, HD artist thumbnail."""
    thumbnails = artist.get("thumbnails") if isinstance(artist, dict) else None
    if not isinstance(thumbnails, list):
        return None
    candidates = []
    for item in thumbnails:
        if not isinstance(item, dict):
            continue
        url = _thumbnail_url(item)
        width = item.get("width")
        height = item.get("height")
        try:
            width = int(width)
            height = int(height or 0)
        except (TypeError, ValueError):
            continue
        if url and width >= 1280 and (not height or width >= height * 1.35):
            candidates.append((width * max(height, 1), width, url))
    return max(candidates, default=None)[2] if candidates else None


def _get_provider():
    """Resolve the app's singleton provider only when a request arrives."""
    try:
        from .app import get_yt
    except ImportError:
        from app import get_yt
    return get_yt()


def _find_downloaded_file(prefix: Path) -> Path | None:
    files = [path for path in prefix.parent.glob(f"{prefix.name}.*") if path.is_file()]
    return max(files, key=lambda path: path.stat().st_mtime_ns, default=None)


def _generate_loop(artist_id: str, artist_name: str) -> None:
    """Download and post-process one eight-second, video-only loop."""
    safe_id = _safe_artist_id(artist_id)
    if not safe_id or not artist_name:
        return
    final_path = LOOP_DIR / f"{safe_id}.mp4"
    if final_path.is_file() and final_path.stat().st_size > 0:
        return

    temp_prefix = LOOP_DIR / f".{safe_id}.download"
    try:
        yt_dlp = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        if not yt_dlp:
            print("Theatre backdrop loop skipped: yt-dlp is not installed", flush=True)
            return
        for old in LOOP_DIR.glob(f"{temp_prefix.name}.*"):
            try:
                old.unlink()
            except OSError:
                pass

        # This is intentionally an argument list, not shell=True: artist names
        # are user/provider data and must never become command syntax.
        command = [
            yt_dlp,
            f"ytsearch1:{artist_name} official music video",
            "--download-sections", "*00:35-00:43",
            "--force-keyframes-at-cuts",
            "-f", "bestvideo[height<=720][ext=mp4]/bestvideo[height<=720]",
            "-o", f"{temp_prefix}.%(ext)s",
            "--quiet",
            "--no-warnings",
            "--no-playlist",
            "--merge-output-format", "mp4",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"Theatre backdrop loop failed for {artist_name!r}: {result.stderr.strip()}", flush=True)
            return

        source = _find_downloaded_file(temp_prefix)
        if not source:
            return
        ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if ffmpeg:
            stripped = LOOP_DIR / f".{safe_id}.stripped.mp4"
            strip_result = subprocess.run([
                ffmpeg, "-y", "-i", str(source),
                "-map", "0:v:0", "-an", "-c:v", "copy",
                "-movflags", "+faststart", str(stripped),
            ], capture_output=True, text=True, timeout=120)
            if strip_result.returncode != 0 or not stripped.is_file() or stripped.stat().st_size == 0:
                print(f"Theatre backdrop post-process failed for {artist_name!r}: {strip_result.stderr.strip()}", flush=True)
                return
            os.replace(str(stripped), str(final_path))
        else:
            # The selected format is video-only, so this remains audio-free.
            # Without ffmpeg faststart cannot be rewritten, but serving the
            # cache is still preferable to failing the entire Theatre surface.
            os.replace(str(source), str(final_path))
    except subprocess.TimeoutExpired:
        print(f"Theatre backdrop loop timed out for {artist_name!r}", flush=True)
    except OSError as exc:
        print(f"Theatre backdrop loop unavailable for {artist_name!r}: {exc}", flush=True)
    finally:
        for old in LOOP_DIR.glob(f".{safe_id}.*"):
            try:
                old.unlink()
            except OSError:
                pass
        with _LOOP_JOBS_LOCK:
            _LOOP_JOBS.discard(safe_id)


def _start_loop_job(artist_id: str, artist_name: str) -> None:
    safe_id = _safe_artist_id(artist_id)
    if not safe_id:
        return
    with _LOOP_JOBS_LOCK:
        if safe_id in _LOOP_JOBS:
            return
        _LOOP_JOBS.add(safe_id)
    threading.Thread(
        target=_generate_loop,
        args=(safe_id, artist_name),
        name=f"theatre-loop-{safe_id}",
        daemon=True,
    ).start()


@media_engine_bp.get("/api/media/backdrop")
def media_backdrop():
    """Return cached loop + HD artist art and schedule missing loop work."""
    artist_id = str(request.args.get("artistId") or request.args.get("artist_id") or "").strip()
    artist_name = str(request.args.get("artistName") or request.args.get("artist_name") or "").strip()
    safe_id = _safe_artist_id(artist_id or artist_name)
    if not safe_id:
        return jsonify({"loopUrl": None, "backdropUrl": None})

    backdrop_url = None
    if artist_id:
        try:
            provider = _get_provider()
            if provider is not None:
                backdrop_url = _artist_backdrop(provider.get_artist(artist_id))
        except Exception as exc:
            print(f"Artist backdrop lookup failed for {artist_id!r}: {exc}", flush=True)

    cached = LOOP_DIR / f"{safe_id}.mp4"
    loop_url = _loop_url(safe_id) if cached.is_file() and cached.stat().st_size > 0 else None
    if loop_url is None and artist_name:
        _start_loop_job(safe_id, artist_name)
    return jsonify({"loopUrl": loop_url, "backdropUrl": backdrop_url})


@media_engine_bp.get("/media/loops/<path:filename>")
def media_loop(filename):
    """Serve only files from the generated loop cache."""
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith(".mp4"):
        return jsonify({"error": "Invalid loop filename"}), 400
    return send_from_directory(LOOP_DIR, safe_name, mimetype="video/mp4", conditional=True)
