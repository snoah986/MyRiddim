# MyRiddim (ytm-player) — Complete App Manifest

Everything the app is, everything it does, how and why it runs the way it does. Written from the actual code in this checkout (branch `main`), not from intention.

---

## 1. What This Is

**MyRiddim** (`ytm-player` v1.0.0, Tauri identifier `com.local.ytmplayer`) is a local-first YouTube Music desktop client: a Svelte frontend backed by a Python Flask server, packaged as a native Windows desktop app via Tauri. It streams from YouTube (yt-dlp), optionally cross-checks SoundCloud, caches audio locally in SQLite + disk, and adds features YouTube Music doesn't have: a dual-deck gapless/crossfade engine, word-level karaoke lyrics with video-intro offset correction, a LAN party jukebox, a mobile remote, and local listening analytics that feed back into recommendations.

**The three layers:**

| Layer | Tech | Where |
|---|---|---|
| Desktop shell | Tauri v2 (Rust) | `src-tauri/` |
| Frontend | Svelte 5 + Vite (~4,000 lines across 21 components/modules) | `src/` |
| Backend | Python Flask (single 3,822-line `app.py` + 6 focused modules), SQLite, yt-dlp, ytmusicapi | `backend/` |

The Rust shell spawns the Python backend as a child process (PyInstaller sidecar `ytm-backend` in packaged builds, `python backend/app.py` in dev), kills it on exit (no orphaned process holding port 5178), and exposes a `restart_backend` command to the UI.

---

## 2. Every Feature, By Area

### 2.1 Playback Engine (`src/lib/audio.js`, 299 lines)
- **Dual-deck Web Audio graph.** Two `<audio>` elements (Deck A/B), each through its own GainNode → master gain → volume-normalization gain → AnalyserNode → destination. One element is "live" (its timeline/events are what the UI sees); the other is the preload/crossfade target.
- **Gapless crossfade.** Near track end, the next stream URL (preloaded up to 15 s ahead) is mounted on the idle deck; at the crossfade window the gains ramp linearly over the configured duration (0–12 s, default 4 s, toggleable). At fade end the incoming deck is adopted *without restarting it* — `playTrack` recognizes the gapless handoff (`audio.gapFilled`) and calls `adoptGapless`, so the song you heard during the fade never restarts from 0:00.
- **Volume normalization** (optional): every 250 ms the analyser's RMS is compared to a target level and a dedicated gain node eases toward it (slow attack/release, never pumps).
- **Hardware DAC warm-up:** an inaudible looping silent buffer keeps the Windows audio endpoint awake — no 200–400 ms WASAPI resume delay.
- **Unified audio-state lock** (`playTrack`): monotonic `playbackRequest` counter + `AbortController` per request. A new request aborts the in-flight fetch and clears both media buffers; stale responses are discarded; the backend's returned `video_id` must match the requested id (mismatch = refused, never played).
- **Failure policy:** crossfade emits a synthetic `ended` so the queue advances exactly once; stream failures auto-advance only on *definitive* refusals — rate-limits (429) and dead-proxy HTML 500s are transient: toast + keep position, never cascade-skip the queue.

### 2.2 Queue (`src/lib/queue.js`, 132 lines)
- Single Svelte store `{ history, nowPlaying, upNext, repeat, shuffle }`, persisted to `localStorage['ymt.queue']` on every change and rehydrated on launch.
- Operations: seed, selectNext/Previous, playUpcoming (jump), playNext (prepend), addToQueue (append, deduped), appendTracks (bulk), remove/clear/reorder (drag-and-drop), party-queue reconciliation, shuffle, repeat cycle (off → all → one).
- Auto-radio top-up: when ≤2 tracks remain, recommendations backfill the queue (~1.2 s debounce).
- Playback Manager drawer: History / Up Next / Recommended tabs, drag-reorder, per-row remove + context menu, hold-to-clear manual queue (0.8 s).

### 2.3 Home / Library (`src/components/HomeView.svelte` + backend feeds)
- **Shelves:** Now-playing hero (with Start Mix), Quick picks, Fresh Discoveries (2:1 discovery/deep-cut interleave seeded by the current track), Heavy rotation, In rotation this month, Because you're playing this, Personal mix (locally computed), Recently played playlists, Smart collections, Your playlists.
- **YTM native multi-shelf feed** (`/api/ytm/feed`) mirrors YouTube Music's own home shelves.
- **Universal "Start Mix"** on every card/row (hover pill): algorithmic radio from that seed, replaces the queue, plays immediately.
- **Smart playlists:** rule-based collections (SQLite `smart_playlists`) that stay fresh as history changes.
- **Views:** Home, Recently played, Favorites, Discover, Listening stats; categorical search shelves (Songs/Artists/Albums/Playlists); artist pages with favorite toggle; album pages; mood playlists; entity routing everywhere.

### 2.4 Theatre Mode (`src/pages/TheatreMode.svelte`, 1,298 lines — the showpiece)
- **Centered editorial stage** over an album-art-sampled mesh backdrop (gradient orbs + film grain), full-bleed 16:9 native `<video>` in video mode.
- **Native video:** companion video resolved per track (`/api/track-video`, duration-matched fallback search + SQLite persistence so lookups never repeat); progressive MP4-first 1080p ladder with a relaxed tail (`worst[ext=webm]/worst`) so webm-only videos still resolve; the video element mounts at full size *before* the source attaches; blurred ambient backdrop mirror in lyrics mode.
- **Depth-of-field kinetic lyrics:** LRCLIB-first synced lyrics (ytmusic fallback), word-level YRC cadence lines (NetEase YRC + `cadence_engine`), active-line highlight, auto-scroll driven by rAF reading the **live audio deck's clock**, click-to-seek, per-track offset persistence, anticipation lead. All timestamps are studio-audio-referenced; video mode shifts the clock (`AudioTime = VideoTime − introOffset`), never the lyric data.
- **Cinematic intro offset engine (4-tier waterfall):** SponsorBlock `music_offtopic` → yt-dlp chapters → YouTube transcript matching → duration-delta fallback (`needs_sync` + "tap to sync beat" card; **S** key or click saves a manual offset). Gated by a ≤3 s duration-delta check so studio audio is never falsely shifted. Persisted in `video_offsets`; manual ±0.5 s (video) / ±0.2 s (audio) nudge pills.
- **Floating glass transport capsule** with 3.5 s inactivity cinema fade (any pointer/key wakes it), **slide-over queue drawer** (Recommended tab, infinite scroll, hold-to-flush, "Saved to playlist" toast), frosted top bar with close chevron + source label.

### 2.5 Party Mode (LAN jukebox — `backend/party.py`, 388 lines)
- Host-side `PartyStore`: rooms live only on the host; guests join via `http://<LAN-IP>:5178/mobile?party=<CODE>` (QR code in the host UI; invite URL always uses the real adapter IP, never loopback).
- Roles & permissions, guest quotas, request cooldowns, optional approval, upvoting with priority ordering, duplicate blocking, max song duration, democratic skip (threshold from connected guests), kick, live settings, graceful end.
- Host UI polls the same `/api/party/*` routes guests use — one rulebook for both transports. Guest page (`mobile.html`) is a PWA (manifest + service worker) with a visible connection-error fallback and retry.

### 2.6 Mobile Remote (LAN, distinct from Party)
- `/api/remote/state` GET/POST + `/api/remote/command` + ack: a phone sees what's playing and controls your own session (play/pause/next/prev/seek/volume).

### 2.7 Desktop-Native Layer (Tauri)
- Frameless window (`decorations: false`), maximized, `#09090b`, min 980 px; window-state persistence across launches (`tauri-plugin-window-state`).
- **System tray:** Play/Pause, Next, Previous, Show/Hide, Quit — media actions emit events the webview maps onto the engine.
- **Media Session API:** OS media keys + taskbar thumbnail controls (SMTC on Windows).
- **Auto-updater (wired, unsigned):** `tauri-plugin-updater` + `tauri-plugin-process` registered, GitHub latest.json endpoint, `createUpdaterArtifacts: true`, Settings → Software Updates UI (background check, manual check, install progress, relaunch). **Release blocker: no updater `pubkey` committed and empty s
