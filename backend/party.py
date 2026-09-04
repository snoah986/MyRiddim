"""Party Mode: the host-side jukebox engine.

One in-memory PartyStore owns all party state. Rooms live only on the host
machine; guests talk to it through /api/party/* routes (LAN) or through an
edge relay that mirrors the same JSON messages to the host (cloud). The host
UI polls the same routes it serves, so both transports share one rulebook:
roles, queue quotas, request cooldowns, optional approval, and upvotes.

Every mutating call returns the (possibly empty) list of playback commands the
desktop player should execute, in order. The host frontend applies them to its
existing remote-command handler, so Party Mode needs no second playback path.
"""
import secrets
import threading
import time
from collections import deque

# --- Rule defaults (host can override per room) ---
MAX_UNPLAYED_PER_GUEST = 3
REQUEST_COOLDOWN_SECONDS = 30

# role -> what the role may do
ROLE_PERMISSIONS = {
    "guest": {"request"},
    "dj": {"request", "vote"},
    "co_dj": {"request", "vote", "skip"},
    "muted": set(),
}

ROOM_LIFETIME_SECONDS = 6 * 60 * 60  # rooms die with the host session anyway


def _now() -> float:
    return time.time()


class PartyGuest:
    __slots__ = ("id", "name", "role", "joined_at", "last_seen", "last_request_at")

    def __init__(self, guest_id: str, name: str) -> None:
        self.id = guest_id
        self.name = name
        self.role = "guest"
        self.joined_at = _now()
        self.last_seen = _now()
        self.last_request_at = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "connected": (_now() - self.last_seen) < 30,
        }


class PartyTrack:
    __slots__ = ("video_id", "title", "artist", "thumbnail", "duration", "requested_by", "requested_by_name", "votes", "status", "created_at")

    def __init__(self, track: dict, guest) -> None:
        self.video_id = track.get("videoId") or track.get("id") or ""
        self.title = track.get("title") or "Untitled"
        self.artist = track.get("artist") or ""
        self.thumbnail = track.get("thumbnail") or ""
        self.duration = track.get("duration") or ""
        self.requested_by = guest.id if guest else None
        self.requested_by_name = guest.name if guest else "Host"
        self.votes = set()
        self.status = "pending"  # pending | queued | played | rejected
        self.created_at = _now()

    def to_dict(self) -> dict:
        return {
            "videoId": self.video_id,
            "title": self.title,
            "artist": self.artist,
            "thumbnail": self.thumbnail,
            "duration": self.duration,
            "requested_by": self.requested_by_name,
            "votes": len(self.votes),
            "status": self.status,
        }


class PartyRoom:
    def __init__(self, code: str, host_name: str) -> None:
        self.code = code
        self.host_name = host_name
        self.created_at = _now()
        self.guests: dict[str, PartyGuest] = {}
        self.tracks: dict[str, PartyTrack] = {}
        self.settings = {
            "require_approval": False,
            "max_unplayed_per_guest": MAX_UNPLAYED_PER_GUEST,
            "cooldown_seconds": REQUEST_COOLDOWN_SECONDS,
            "democratic_upvoting": True,
        }
        self.history: deque = deque(maxlen=100)
        self.lock = threading.RLock()

    # -- rule helpers -----------------------------------------------------
    def permissions_for(self, guest: PartyGuest) -> set:
        return set(ROLE_PERMISSIONS.get(guest.role, set()))

    def unplayed_count(self, guest_id: str) -> int:
        return sum(
            1 for track in self.tracks.values()
            if track.requested_by == guest_id and track.status == "queued"
        )

    def remaining_cooldown(self, guest: PartyGuest) -> int:
        window = self.settings["cooldown_seconds"]
        elapsed = _now() - guest.last_request_at
        return max(0, int(window - elapsed)) if elapsed < window else 0

    # -- views ------------------------------------------------------------
    def public_state(self) -> dict:
        ordered = sorted(
            self.tracks.values(),
            key=lambda t: (t.status != "pending", -len(t.votes), t.created_at),
        )
        pending = [t.to_dict() for t in ordered if t.status == "pending"]
        queued = [t.to_dict() for t in ordered if t.status == "queued"]
        return {
            "code": self.code,
            "host_name": self.host_name,
            "settings": dict(self.settings),
            "guests": [g.to_dict() for g in self.guests.values()],
            "pending": pending,
            "queue": queued,
            "history": list(self.history),
        }


class PartyStore:
    """All rooms on this host. In-memory only: restart = new room, which is
    the right durability trade for a party."""

    def __init__(self) -> None:
        self._rooms: dict[str, PartyRoom] = {}
        self._lock = threading.RLock()

    # -- rooms ------------------------------------------------------------
    def create_room(self, host_name: str) -> PartyRoom:
        with self._lock:
            code = "RIDD" + secrets.token_hex(2).upper()  # e.g. RIDD-84 style, 4 hex chars
            room = PartyRoom(code, host_name or "Host")
            self._prune()
            self._rooms[code] = room
            return room

    def get_room(self, code: str) -> PartyRoom | None:
        with self._lock:
            room = self._rooms.get((code or "").upper())
            if room and (_now() - room.created_at) > ROOM_LIFETIME_SECONDS:
                del self._rooms[code]
                return None
            return room

    def close_room(self, code: str) -> bool:
        with self._lock:
            return self._rooms.pop((code or "").upper(), None) is not None

    def _prune(self) -> None:
        expired = [code for code, room in self._rooms.items()
                   if (_now() - room.created_at) > ROOM_LIFETIME_SECONDS]
        for code in expired:
            del self._rooms[code]

    # -- guests -----------------------------------------------------------
    @staticmethod
    def join(room: PartyRoom, name: str) -> PartyGuest:
        with room.lock:
            name = (name or "").strip()[:24] or "Guest"
            guest = PartyGuest(secrets.token_hex(8), name)
            room.guests[guest.id] = guest
            return guest

    @staticmethod
    def set_role(room: PartyRoom, guest_id: str, role: str) -> bool:
        if role not in ROLE_PERMISSIONS:
            return False
        with room.lock:
            guest = room.guests.get(guest_id)
            if not guest:
                return False
            guest.role = role
            return True

    @staticmethod
    def kick(room: PartyRoom, guest_id: str) -> bool:
        with room.lock:
            return room.guests.pop(guest_id, None) is not None

    @staticmethod
    def touch(room: PartyRoom, guest_id: str) -> PartyGuest | None:
        with room.lock:
            guest = room.guests.get(guest_id)
            if guest:
                guest.last_seen = _now()
            return guest

    # -- requests ---------------------------------------------------------
    @staticmethod
    def request_track(room: PartyRoom, guest: PartyGuest, track: dict) -> tuple[dict | None, str | None]:
        """Returns (queued_track_view, error). On success also returns the
        playback command list via the route layer."""
        with room.lock:
            if "request" not in room.permissions_for(guest):
                return None, "You do not have permission to request tracks"
            cooldown = room.remaining_cooldown(guest)
            if cooldown:
                return None, f"Wait {cooldown}s before requesting again"

            video_id = (track.get("videoId") or track.get("id") or "").strip()
            if not video_id:
                return None, "Track has no id"
            key = video_id
            if key in room.tracks and room.tracks[key].status in ("pending", "queued"):
                return None, "Already requested"

            quota = room.settings["max_unplayed_per_guest"]
            if quota and room.unplayed_count(guest.id) >= quota:
                return None, f"Track limit reached ({quota} unplayed)"

            entry = PartyTrack({**track, "videoId": video_id}, guest)
            guest.last_request_at = _now()
            room.tracks[key] = entry

            if room.settings["require_approval"]:
                entry.status = "pending"
                return entry.to_dict(), None  # host approval flow; no command yet
            entry.status = "queued"
            return entry.to_dict(), None

    @staticmethod
    def approve(room: PartyRoom, video_id: str) -> dict | None:
        with room.lock:
            entry = room.tracks.get(video_id)
            if not entry or entry.status != "pending":
                return None
            entry.status = "queued"
            return entry.to_dict()

    @staticmethod
    def reject(room: PartyRoom, video_id: str) -> bool:
        with room.lock:
            entry = room.tracks.get(video_id)
            if not entry or entry.status != "pending":
                return False
            entry.status = "rejected"
            return True

    @staticmethod
    def upvote(room: PartyRoom, video_id: str, guest: PartyGuest) -> int | None:
        # Democratic upvoting lets every guest vote; when disabled, only dj+
        # roles retain the privilege (a muted guest can never vote).
        permissions = room.permissions_for(guest)
        if "vote" not in permissions and not (room.settings.get("democratic_upvoting") and "request" in permissions):
            return None
        with room.lock:
            entry = room.tracks.get(video_id)
            if not entry or entry.status != "queued":
                return None
            if guest.id in entry.votes:
                entry.votes.discard(guest.id)
            else:
                entry.votes.add(guest.id)
            return len(entry.votes)

    @staticmethod
    def mark_played(room: PartyRoom, video_id: str) -> None:
        with room.lock:
            entry = room.tracks.get(video_id)
            if entry and entry.status == "queued":
                entry.status = "played"
                room.history.append(entry.to_dict())


PARTY_STORE = PartyStore()
