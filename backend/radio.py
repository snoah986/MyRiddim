"""Provider-agnostic radio mix normalization."""


def normalize_radio_tracks(raw_tracks, normalize_track, is_valid_video_id):
    """Map YTMusic radio items to the app track contract.

    ``normalize_track`` is the app's shared metadata adapter; keeping it
    injected avoids a second thumbnail/title policy in this module while
    making radio ordering and duplicate handling independently testable.
    """
    tracks = []
    seen = set()
    for item in raw_tracks or []:
        if not isinstance(item, dict):
            continue
        video_id = str(item.get("videoId") or "").strip()
        if not is_valid_video_id(video_id) or video_id in seen:
            continue
        normalized_item = {
            **item,
            "duration": item.get("duration") or item.get("length", ""),
            "thumbnails": item.get("thumbnails") or item.get("thumbnail") or [],
        }
        track = normalize_track(normalized_item)
        if not track or not track.get("videoId"):
            continue
        track["source"] = "radio_mix"
        seen.add(video_id)
        tracks.append(track)
    return tracks
