"""Canonical track matching and persistence.

The matcher deliberately keeps provider-specific payloads at the edge of the
application. Once a source is ingested, recommendations and playback can work
with the canonical id while retaining every playable provider source.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import string
from typing import Any, Mapping

try:
    from rapidfuzz import fuzz
except ImportError:  # Keep the app usable before the optional dependency is installed.
    from difflib import SequenceMatcher

    class _FallbackFuzz:
        @staticmethod
        def token_sort_ratio(left: str, right: str) -> float:
            def tokens(value: str) -> str:
                return " ".join(sorted(value.split()))
            return SequenceMatcher(None, tokens(left), tokens(right)).ratio() * 100

    fuzz = _FallbackFuzz()


BRACKETED_EXTRAS = re.compile(r"(?:\([^)]*\)|\[[^]]*\])")
PUNCTUATION = str.maketrans({character: " " for character in string.punctuation})


def normalize_metadata(text: Any) -> str:
    """Normalize titles/artists for matching.

    Bracketed release annotations such as ``(feat. X)``, ``[Official Video]``
    and ``(Remastered)`` are intentionally discarded before punctuation and
    whitespace normalization.
    """
    value = str(text or "").lower()
    value = BRACKETED_EXTRAS.sub(" ", value)
    value = value.translate(PUNCTUATION)
    return " ".join(value.split())


def canonical_id(title: Any, artist: Any) -> str:
    """Return a stable id derived from normalized artist + title."""
    value = f"{normalize_metadata(artist)}\x00{normalize_metadata(title)}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _duration(value: Any) -> int:
    try:
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return 0


def _get(value: Mapping[str, Any], key: str, default: Any = None) -> Any:
    """Read both dicts and sqlite3.Row values."""
    try:
        return value[key]
    except (KeyError, IndexError, TypeError):
        return default


def evaluate_match(incoming: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Score one incoming source against one canonical candidate."""
    incoming_duration = _duration(_get(incoming, "duration_sec"))
    candidate_duration = _duration(_get(candidate, "duration_sec"))
    if incoming_duration and candidate_duration and abs(incoming_duration - candidate_duration) > 4:
        return {"score": 0.0, "action": "new", "reason": "duration_gate"}

    incoming_isrc = str(_get(incoming, "isrc") or "").strip().lower()
    candidate_isrc = str(_get(candidate, "isrc") or "").strip().lower()
    if incoming_isrc and candidate_isrc and incoming_isrc == candidate_isrc:
        return {"score": 100.0, "action": "auto", "reason": "isrc"}

    title_score = fuzz.token_sort_ratio(
        normalize_metadata(_get(incoming, "title")), normalize_metadata(_get(candidate, "title_norm"))
    )
    artist_score = fuzz.token_sort_ratio(
        normalize_metadata(_get(incoming, "artist")), normalize_metadata(_get(candidate, "artist_norm"))
    )
    score = (title_score * 0.6) + (artist_score * 0.4)
    action = "auto" if score >= 92 else "review" if score >= 75 else "new"
    return {"score": round(score, 4), "action": action, "reason": "fuzzy"}


def _insert_review(
    db: sqlite3.Connection,
    incoming: Mapping[str, Any],
    candidate_id: str,
    score: float,
) -> None:
    db.execute(
        """INSERT INTO merge_review_queue
           (incoming_source, incoming_source_id, incoming_title, incoming_artist,
            incoming_duration, candidate_canonical_id, confidence_score, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (
            incoming["source"],
            incoming["source_id"],
            str(incoming.get("title") or "Unknown title"),
            str(incoming.get("artist") or "Unknown artist"),
            _duration(incoming.get("duration_sec")),
            candidate_id,
            score,
        ),
    )


def ingest_track(
    db: sqlite3.Connection,
    *,
    source: str,
    source_id: str,
    title: str,
    artist: str,
    duration_sec: int | float | None = 0,
    isrc: str | None = None,
    stream_url: str | None = None,
    preferred_source: str | None = None,
) -> str:
    """Resolve a source into a canonical entity and persist its source row.

    Review-range matches are temporarily attached to their best candidate so
    the library remains deduplicated while ``merge_review_queue`` records the
    decision that still needs user confirmation.
    """
    source = str(source or "").lower().strip()
    if source not in {"youtube", "soundcloud"}:
        raise ValueError("source must be youtube or soundcloud")
    source_id = str(source_id or "").strip()
    if not source_id:
        raise ValueError("source_id is required")
    incoming = {
        "source": source,
        "source_id": source_id,
        "title": str(title or "Unknown title").strip() or "Unknown title",
        "artist": str(artist or "Unknown artist").strip() or "Unknown artist",
        "duration_sec": _duration(duration_sec),
        "isrc": isrc,
    }

    existing_source = db.execute(
        "SELECT canonical_id FROM track_sources WHERE source = ? AND source_id = ?",
        (source, source_id),
    ).fetchone()
    if existing_source:
        canonical = existing_source[0]
        db.execute(
            "UPDATE track_sources SET stream_url = COALESCE(?, stream_url), raw_title = ?, raw_artist = ?, duration_sec = ? WHERE source = ? AND source_id = ?",
            (stream_url, incoming["title"], incoming["artist"], incoming["duration_sec"], source, source_id),
        )
        return canonical

    candidates = db.execute(
        "SELECT id, title_norm, artist_norm, duration_sec, isrc FROM canonical_tracks"
    ).fetchall()
    best = None
    best_match = {"score": 0.0, "action": "new", "reason": "none"}
    for candidate in candidates:
        match = evaluate_match(incoming, candidate)
        if match["score"] > best_match["score"]:
            best, best_match = candidate, match

    if best is not None and best_match["action"] in {"auto", "review"}:
        canonical = str(best["id"])
        if best_match["action"] == "review":
            _insert_review(db, incoming, canonical, best_match["score"])
        if isrc:
            db.execute("UPDATE canonical_tracks SET isrc = COALESCE(isrc, ?) WHERE id = ?", (isrc, canonical))
    else:
        canonical = canonical_id(incoming["title"], incoming["artist"])
        # A hash collision is extraordinarily unlikely, but a changed duration
        # should never overwrite a different entity.
        if db.execute("SELECT 1 FROM canonical_tracks WHERE id = ?", (canonical,)).fetchone():
            canonical = hashlib.sha256(f"{canonical}\x00{source}\x00{source_id}".encode()).hexdigest()
        db.execute(
            """INSERT INTO canonical_tracks
               (id, title_norm, artist_norm, duration_sec, isrc, preferred_source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                canonical,
                normalize_metadata(incoming["title"]),
                normalize_metadata(incoming["artist"]),
                incoming["duration_sec"],
                isrc,
                preferred_source if preferred_source in {"youtube", "soundcloud"} else source,
            ),
        )

    db.execute(
        """INSERT INTO track_sources
           (canonical_id, source, source_id, raw_title, raw_artist, duration_sec, stream_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (canonical, source, source_id, incoming["title"], incoming["artist"], incoming["duration_sec"], stream_url),
    )
    _prefer_source(db, canonical, source, preferred_source)
    return canonical


def _prefer_source(db: sqlite3.Connection, canonical_id_value: str, source: str, preferred: str | None) -> None:
    if preferred in {"youtube", "soundcloud"}:
        db.execute("UPDATE canonical_tracks SET preferred_source = ? WHERE id = ?", (preferred, canonical_id_value))
        return
    row = db.execute("SELECT preferred_source FROM canonical_tracks WHERE id = ?", (canonical_id_value,)).fetchone()
    if row and row[0] == "soundcloud" and source == "youtube":
        return
    db.execute("UPDATE canonical_tracks SET preferred_source = ? WHERE id = ?", (source, canonical_id_value))


def backfill_listens(db: sqlite3.Connection) -> int:
    """Create canonical/source rows for legacy YouTube listening history."""
    rows = db.execute(
        "SELECT id, video_id, title, artist, album, listen_duration_seconds FROM listens WHERE canonical_id IS NULL"
    ).fetchall()
    count = 0
    for row in rows:
        canonical = ingest_track(
            db,
            source="youtube",
            source_id=row["video_id"],
            title=row["title"],
            artist=row["artist"],
            # This legacy field is amount heard, not recording duration; zero
            # keeps the duration gate open during migration.
            duration_sec=0,
        )
        db.execute("UPDATE listens SET canonical_id = ?, source = 'youtube', source_id = ? WHERE id = ?", (canonical, row["video_id"], row["id"]))
        count += 1
    return count


__all__ = ["canonical_id", "evaluate_match", "ingest_track", "normalize_metadata", "backfill_listens"]
