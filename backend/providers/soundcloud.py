"""SoundCloud source adapter.

SoundCloud's public web API requires a client id. The adapter uses the public
v2 endpoints and accepts an OAuth bearer token when available. It is inert
until SOUNDCLOUD_CLIENT_ID is configured, so YouTube-only installations keep
working without any new authentication flow.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import requests

from .base import MusicProvider


class SoundCloudProvider(MusicProvider):
    name = "soundcloud"
    base_url = "https://api-v2.soundcloud.com"

    def __init__(self, client_id: str | None = None, oauth_token: str | None = None, timeout: float = 12):
        self.client_id = client_id or os.getenv("SOUNDCLOUD_CLIENT_ID")
        self.oauth_token = oauth_token or os.getenv("SOUNDCLOUD_OAUTH_TOKEN")
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.client_id)

    def _request(self, path: str, **params: Any) -> Any:
        if not self.enabled:
            return []
        params = {key: value for key, value in params.items() if value is not None}
        params["client_id"] = self.client_id
        headers = {"Authorization": f"OAuth {self.oauth_token}"} if self.oauth_token else {}
        response = self.session.get(f"{self.base_url}{path}", params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        user = raw.get("user") or {}
        duration = raw.get("duration")
        try:
            duration_sec = max(0, int(round(float(duration or 0) / 1000)))
        except (TypeError, ValueError):
            duration_sec = 0
        artwork = raw.get("artwork_url") or user.get("avatar_url")
        return {
            "source": "soundcloud",
            "source_id": str(raw.get("id") or ""),
            "title": str(raw.get("title") or "Unknown title"),
            "artist": str(user.get("username") or raw.get("publisher_metadata", {}).get("artist") or "Unknown artist"),
            "duration_sec": duration_sec,
            "isrc": (raw.get("publisher_metadata") or {}).get("isrc") or raw.get("isrc"),
            "thumbnail": artwork,
            "permalink_url": raw.get("permalink_url"),
            "raw": raw,
        }

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        data = self._request("/search/tracks", q=query, limit=min(max(int(limit), 1), 200))
        return [self.normalize(item) for item in (data.get("collection", []) if isinstance(data, dict) else [])]

    def get_stream_url(self, track_id: str) -> str | None:
        data = self._request(f"/tracks/{track_id}")
        media = data.get("media") or {}
        transcodings = media.get("transcodings") or []
        # Prefer progressive MP3/AAC so the browser does not need an HLS
        # demuxer. If unavailable, return the first valid transcoding endpoint.
        ordered = sorted(transcodings, key=lambda item: (item.get("format", {}).get("protocol") != "progressive", item.get("format", {}).get("mime_type", "")))
        for transcoding in ordered:
            if transcoding.get("url"):
                resolved = self._request_url(transcoding["url"])
                if resolved:
                    return resolved
        return None

    def _request_url(self, url: str) -> str | None:
        if not self.enabled:
            return None
        params = {"client_id": self.client_id}
        headers = {"Authorization": f"OAuth {self.oauth_token}"} if self.oauth_token else {}
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("url") if isinstance(data, dict) else None

    def get_user_saved(self) -> list[dict[str, Any]]:
        """Return liked tracks, reposts, and tracks from the user's playlists."""
        if not self.oauth_token:
            return []
        saved: list[dict[str, Any]] = []
        for path in ("/users/me/track_likes/tracks", "/users/me/reposts/tracks"):
            data = self._request(path, limit=200)
            collection = data.get("collection", []) if isinstance(data, dict) else []
            for item in collection:
                raw = item.get("track") if isinstance(item, dict) and item.get("track") else item
                if isinstance(raw, dict):
                    saved.append(self.normalize(raw))
        playlists = self._request("/users/me/playlists", limit=200)
        for playlist in (playlists.get("collection", []) if isinstance(playlists, dict) else []):
            playlist_id = playlist.get("id")
            if not playlist_id:
                continue
            data = self._request(f"/playlists/{playlist_id}/tracks", limit=200)
            for item in (data.get("collection", []) if isinstance(data, dict) else []):
                raw = item.get("track") if isinstance(item, dict) and item.get("track") else item
                if isinstance(raw, dict):
                    saved.append(self.normalize(raw))
        unique: dict[str, dict[str, Any]] = {}
        for item in saved:
            if item["source_id"]:
                unique[item["source_id"]] = item
        return list(unique.values())
