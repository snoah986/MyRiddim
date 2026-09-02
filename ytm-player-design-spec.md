# My Music — App Design Spec

A personal, lightweight, ad-free desktop player for YouTube Music, built with
Tauri + a Python backend. This doc captures the full feature set and
architecture before implementation.

---

## 1. Core Playback

- **Full interactive queue** — not a generic list. Drag-to-reorder, click to
  jump to any track, visually shows what's playing / up next / recently
  played. This is a first-class UI panel, not an afterthought.
- **Auto-play** — continues to the next track in the queue/playlist automatically.
- **Shuffle & repeat** — repeat-one, repeat-all, shuffle toggle, standard behavior.
- **Search** — full YouTube Music search from inside the app (songs, albums,
  artists, playlists), not just your existing library.
- **Playlist creation/editing** — create new playlists, add/remove tracks,
  reorder, rename, delete — mirrored back to your real YouTube Music account
  via `ytmusicapi`'s write endpoints.
- **Video → MP3 conversion** — when a "playlist" source is actually a video
  (not a proper Music track), the app extracts the audio as MP3 and embeds
  the thumbnail as cover art (via yt-dlp's audio-extraction + ffmpeg,
  metadata written with `mutagen`). This becomes a normal cached "song" in
  every sense after that — playable, cacheable, has artwork.

---

## 2. Library & Caching

- **All playlist types supported** — YouTube Music playlists AND regular
  YouTube playlists that contain music/videos. Both normalize into the same
  internal track format after processing.
- **Local caching strategy**:
  - Metadata (titles, artist, artwork, playlist structure) is cached locally
    in a small SQLite database on first load.
  - On each app launch, it does a lightweight diff-check against YouTube
    Music (new tracks / removed tracks / renamed playlists) and updates only
    what changed — not a full re-download every time.
  - A manual "Refresh Library" button forces an immediate full sync.
  - Audio itself: streamed live by default; a track only gets a persisted
    local file if you've played it before recently (recently-played cache,
    Q19) or if it went through the video→MP3 conversion step above.
  - Cache has a configurable size limit (default e.g. 2GB) with least-recently-played eviction.

---

## 3. Theatre Mode (the centerpiece)

- **Full-screen only** — this is the primary "watching this player" experience.
- **Dynamic background**: album art blurred + animated color gradient
  extracted from the artwork's dominant colors (similar approach to Apple
  Music/Spotify Canvas) — recalculated per track.
- **Vibe adapts to the song** — the color palette and animation pacing pull
  from the album art's actual colors, so a moody track and a bright track
  visually feel different automatically. No manual theme picking needed.
- **Artwork auto-loads** once a track is cached (from YouTube thumbnail, or
  embedded MP3 art for converted videos).
- **Lyrics panel**: synced lyrics with the current line highlighted, past/
  future lines dimmed. Falls back to plain (unsynced) lyrics if no LRC
  version exists anywhere.
- **Click-to-seek on lyrics** — clicking a lyric line jumps playback to that
  timestamp.
- **Lyrics auto-sourced** from best available provider (LRCLIB first for
  synced, Musixmatch/genius-style fallback for plain) — app tries multiple
  sources silently, user never has to pick.

---

## 4. System Integration

- **Taskbar media controls** (Windows) — shows now-playing + play/pause/skip
  directly in the taskbar thumbnail, like Spotify.
- **Global media key support** — physical/keyboard media keys control
  playback even when the app isn't focused.
- **Discord Rich Presence** — shows what you're listening to.
- **Manual launch by default** — no auto-start on login, but a Settings
  toggle to enable "Start with Windows" for later if you want it.
- **System tray** — minimizing keeps it playing in the tray instead of
  quitting; this is a toggle in Settings (default: off, so closing the
  window actually closes the app until you turn it on).

---

## 5. Settings Panel

Centralized settings screen covering:
- Start with Windows (on/off)
- Minimize to tray vs. quit on close (on/off)
- Reduce motion / disable animated backgrounds (on/off — for battery saving)
- Cache size limit
- Audio quality preference (if multiple stream qualities available)
- Discord Rich Presence (on/off)
- Account / re-authenticate with YouTube Music

---

## 6. Offline Downloads (Phase 2 — after MVP)

Not in the initial build. Once the core app is solid, add an explicit
"Download for offline" option per track/playlist, separate from the
recently-played cache — a deliberate, permanent local copy.

---

## 7. Architecture

```
┌─────────────────────────────┐
│   Tauri App (Rust shell)    │
│  ┌────────────────────────┐ │
│  │  Frontend (HTML/JS/CSS) │ │  <- UI: queue, theatre mode, search, settings
│  │  or a lightweight        │ │
│  │  framework like Svelte   │ │
│  └───────────┬────────────┘ │
│              │ localhost API │
│  ┌───────────▼────────────┐ │
│  │  Python backend sidecar │ │  <- launched automatically by Tauri
│  │  (Flask)                │ │
│  │  - ytmusicapi (library, │ │
│  │    search, playlist CRUD)│ │
│  │  - yt-dlp (streaming +   │ │
│  │    video->mp3 conversion)│ │
│  │  - syncedlyrics (lyrics) │ │
│  │  - SQLite (local cache)  │ │
│  │  - mutagen (mp3 metadata)│ │
│  └─────────────────────────┘ │
└──────────────────────────────┘
```

**Why this shape:**
- Tauri keeps RAM/disk footprint small (native webview, no bundled Chromium) —
  directly addresses the "th-ch eats too much RAM" complaint.
- Python backend reuses mature, actively maintained libraries instead of
  reimplementing YouTube's internal API and audio extraction from scratch.
- Backend runs as a Tauri "sidecar" — starts/stops automatically with the
  app, so you never see a terminal window.

---

## 8. Frontend framework choice

Plain HTML/JS (what we prototyped) will get painful once we add: a real
drag-to-reorder queue, live search-as-you-type, a settings panel, and
theatre mode animations. Recommend moving to **Svelte** at this point —
lighter than React, compiles to small vanilla JS (fits the "lightweight"
goal), and pairs natively with Tauri's official Svelte template. You said
you're more toward beginner-with-some-experience — Svelte's syntax is closer
to plain HTML/CSS/JS than React's is, so it should be an easier ramp, not a
harder one.

---

## 9. Build Plan (phased)

**Phase 1 — Foundation**
- Set up Tauri + Svelte project shell
- Wire up Python backend as a sidecar
- Get playlists loading + basic playback working (what we already prototyped, ported over)

**Phase 2 — Real queue & controls**
- Interactive queue UI (reorder, jump, remove)
- Auto-play, shuffle, repeat
- Taskbar controls + media keys

**Phase 3 — Search & playlist management**
- YouTube Music search
- Create/edit/delete playlists, add/remove tracks (writes back to your account)

**Phase 4 — Theatre mode**
- Full-screen layout
- Dynamic color extraction from album art + animated background
- Synced lyrics with active-line highlight + click-to-seek
- Plain lyrics fallback

**Phase 5 — Caching & conversion**
- SQLite local cache + diff-sync on launch
- Video → MP3 conversion pipeline with embedded artwork
- Recently-played local audio caching with eviction

**Phase 6 — System polish**
- Settings panel (all toggles from section 5)
- System tray behavior
- Discord Rich Presence

**Phase 7 (later, optional)**
- Explicit offline downloads separate from cache

---

## 10. Open technical questions to resolve when we start building
- Exact color-extraction approach for theatre mode (canvas pixel sampling vs. a small library like `node-vibrant` / `colorthief`)
- Whether playlist writes (create/edit) go through `ytmusicapi`'s existing write support or need extra handling for edge cases
- SQLite schema for cache (tracks, playlists, cache metadata, eviction timestamps)

---

This is the reference doc for the whole build — when we start Phase 1, we'll
work off this file so nothing gets lost between sessions.
