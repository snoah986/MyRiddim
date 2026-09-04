"""Low-memory syllable lyric ingestion and cadence fallback.

This module intentionally contains no audio model or forced aligner.  YRC
payloads are parsed into small plain dictionaries, and ordinary line-timed
lyrics are expanded into approximate word spans using a phonotactic heuristic.
"""
import re
from statistics import median
from urllib.parse import quote_plus

import requests


_LINE_RE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_WORD_RE = re.compile(r"\(([-]?\d+),(\d+),\d+\)([^\(]+)")
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)


def _text(value):
    return " ".join(str(value or "").replace("\\n", " ").split()).strip()


def parse_yrc(yrc_string):
    """Parse NetEase YRC text into line and word timing spans in seconds."""
    lines = []
    for raw_line in str(yrc_string or "").splitlines():
        match = _LINE_RE.match(raw_line.strip())
        if not match:
            continue
        line_start = int(match.group(1)) / 1000.0
        line_duration = int(match.group(2)) / 1000.0
        words = []
        for word_match in _WORD_RE.finditer(match.group(3)):
            word_offset = max(0, int(word_match.group(1))) / 1000.0
            word_duration = max(0, int(word_match.group(2))) / 1000.0
            # Separators are restored between token elements below; trim token
            # padding so upstream spacing cannot turn into doubled gaps.
            word_text = word_match.group(3).strip()
            if not word_text:
                continue
            start = round(line_start + word_offset, 3)
            words.append({
                "text": word_text,
                "start": start,
                "end": round(start + word_duration, 3),
            })
        if words:
            lines.append({
                "start": round(line_start, 3),
                "end": round(line_start + line_duration, 3),
                # YRC token payloads often omit separators; keep words readable
                # in both the plain line fallback and accessibility text.
                "text": " ".join(word["text"].strip() for word in words).strip(),
                "words": words,
            })
    return lines


def fetch_netease_yrc(clean_title, clean_artist, timeout=3.0):
    """Fetch true millisecond lyric spans from NetEase, or return ``None``.

    Both requests are bounded and all provider errors are deliberately hidden
    from playback: YRC is an enhancement, never a dependency for lyrics.
    """
    title = _text(clean_title)
    artist = _text(clean_artist)
    if not title:
        return None
    try:
        query = quote_plus(f"{artist} {title}")
        search_url = (
            "https://music.163.com/api/search/get/web?csrf_token=&"
            f"s={query}&type=1&offset=0&total=true&limit=1"
        )
        response = requests.get(search_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        songs = response.json().get("result", {}).get("songs", [])
        if not songs or not songs[0].get("id"):
            return None
        lyric_url = (
            "https://music.163.com/api/song/lyric?id="
            f"{songs[0]['id']}&lv=1&kv=1&tv=-1&yv=1"
        )
        lyric_response = requests.get(lyric_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        lyric_response.raise_for_status()
        yrc = lyric_response.json().get("yrc", {}).get("lyric")
        parsed = parse_yrc(yrc)
        return parsed or None
    except Exception:
        return None


def _syllables(word):
    """Cheap language-agnostic syllable estimate; no model or large tables."""
    token = re.sub(r"[^\w']", "", str(word or ""), flags=re.UNICODE)
    if not token:
        return 0
    groups = len(_VOWEL_GROUP_RE.findall(token))
    if groups:
        # Silent trailing e is a useful correction for English lyrics.
        if token.lower().endswith("e") and groups > 1 and not token.lower().endswith(("le", "ye")):
            groups -= 1
        return max(1, groups)
    return max(1, round(len(token) / 3))


def _words_for_line(text):
    words = [part for part in re.findall(r"\S+", str(text or "")) if part]
    return [(word, _syllables(word)) for word in words]


def build_cadence_lines(lrc_lines, duration=None, genre_hint=""):
    """Expand line-timed lyrics into approximate word/syllable spans.

    The cadence mode is intentionally conservative.  It estimates syllables per
    second from each line's available window, then allocates that window by
    syllable weight.  Dense lines are treated as rapid-flow (rap/drill-like),
    while sparse lines retain longer melodic word spans.
    """
    if not isinstance(lrc_lines, list):
        return []
    source = []
    for index, item in enumerate(lrc_lines[:400]):
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("time", item.get("start", 0)))
        except (TypeError, ValueError):
            continue
        text = _text(item.get("text"))
        if not text:
            continue
        try:
            next_start = float(lrc_lines[index + 1].get("time", lrc_lines[index + 1].get("start", start + 4))) if index + 1 < len(lrc_lines) else None
        except (TypeError, ValueError, AttributeError):
            next_start = None
        source.append((max(0.0, start), text, next_start))
    if not source:
        return []

    windows = []
    for index, (start, text, next_start) in enumerate(source):
        fallback_end = source[index + 1][0] if index + 1 < len(source) else None
        end = next_start if next_start is not None else fallback_end
        if end is None:
            try:
                end = float(duration)
            except (TypeError, ValueError):
                end = start + 4.0
        end = max(start + 0.35, end)
        words = _words_for_line(text)
        syllable_count = sum(count for _, count in words) or 1
        windows.append((start, end, text, words, syllable_count))

    sps_values = [count / max(0.35, end - start) for start, end, _, _, count in windows]
    typical_sps = median(sps_values) if sps_values else 3.0
    # Genre hint only nudges the cadence, never changes timestamps drastically.
    hint = str(genre_hint or "").lower()
    if any(token in hint for token in ("rap", "drill", "hip hop", "hip-hop")):
        typical_sps = max(typical_sps, 4.5)

    result = []
    for start, end, text, words, syllable_count in windows:
        span = max(0.35, end - start)
        line_sps = syllable_count / span
        # Dense lines need tighter word boundaries; melodic lines keep a small
        # breathing gap at either edge.  This is a presentation hint only.
        density = max(0.65, min(1.25, line_sps / max(1.0, typical_sps)))
        usable_start = start + min(0.08, span * 0.02)
        usable_span = max(0.2, span - (usable_start - start))
        cursor = usable_start
        timed_words = []
        for word, count in words:
            word_span = usable_span * (count / syllable_count)
            word_end = min(end, cursor + word_span * density)
            timed_words.append({
                "text": word,
                "start": round(cursor, 3),
                "end": round(max(cursor + 0.04, word_end), 3),
            })
            cursor = word_end
        result.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
            "words": timed_words,
            "sps": round(line_sps, 2),
            "cadence": "rapid" if line_sps >= 5.5 else "melodic" if line_sps <= 2.5 else "flow",
        })
    return result
