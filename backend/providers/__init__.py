"""External music-source adapters."""

from .base import MusicProvider
from .soundcloud import SoundCloudProvider

__all__ = ["MusicProvider", "SoundCloudProvider"]
