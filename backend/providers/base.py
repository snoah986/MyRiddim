"""Provider contract used by multi-source ingestion and playback routing."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MusicProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_stream_url(self, track_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_user_saved(self) -> list[dict[str, Any]]:
        raise NotImplementedError
