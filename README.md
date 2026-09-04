# Freebuff Desktop / myriddim

A local-first YouTube Music desktop client: Svelte UI, a Flask/ytmusicapi bridge, a low-latency Web Audio player, and an optional Tauri 2 shell. It keeps credentials, listening history, and media cache on the user’s machine.

> **Status:** active development. `v1.2.0` is the latest committed release; the current checkout also contains a large, uncommitted feature pass. Treat unreleased features as experimental until they are split, tested, and committed.

## Highlights

- **OLED Theatre Mode** — centered album art/video stage, sampled artwork mesh, synced lyrics, queue drawer, cinema fade, and crossfade-aware playback.
- **Discovery** — YouTube Music shelves, related-artist exploration, Fresh Discoveries, and one-tap Start Mix.
- **Party Jukebox** — host rooms, guest requests, voting, moderation, quotas, cooldowns, mobile guest UI, and a draft Cloudflare relay.
- **Smart sync** — LRCLIB-first lyrics, YTM fallback, video intro offsets, manual calibration, YRC syllable timing, and a model-free cadence fallback.
- **Local-first playback** — SQLite listening data, a bounded audio cache, same-origin stream proxying, Media Session controls, and dual-deck crossfade.
- **Desktop shell** — frameless Tauri window, custom controls, tray menu, backend sidecar contract, and window-state persistence wiring.

## Architecture

```text
┌──────────────────────────────┐
│ Svelte 5 frontend             │
│ App state · queue · Theatre   │
│ shelves · lyrics · Media API  │
└──────────────┬───────────────┘
               │ HTTP / same-origin proxy
┌──────────────▼───────────────┐
│ Tauri 2 Rust shell (optional) │
│ window · tray · sidecar       │
└──────────────┬───────────────┘
               │ localhost process
┌──────────────▼───────────────┐
│ Python Flask sidecar          │
│ ytmusicapi · yt-dlp · SQLite  │
│ streams · lyrics · party      │
└──────────────┬───────────────┘
               │ outbound, user-authorized providers
       YouTube Music · LRCLIB · NetEase · SponsorBlock
```

The backend is the authority for provider access, credentials, SQLite schemas, stream resolution, and HTTP contracts. `App.svelte` owns user-visible playback and navigation state; `lib/queue.js` owns queue transitions; `lib/audio.js` owns media decks and Web Audio; rendering components receive props and callbacks.

## Requirements

### Local web development

- Node.js 18 or newer
- Python 3.10 or newer
- A valid YouTube Music `browser.json` or OAuth setup
- Network access to YouTube Music and optional lyric providers

### Tauri desktop builds

- Rust stable via [rustup](https://rustup.rs/)
- Windows: Visual Studio Desktop development with C++ / MSVC Build Tools
- macOS: Xcode command-line tools
- Linux: Tauri WebKitGTK dependencies; the CI workflow installs Ubuntu dependencies
- PyInstaller for a bundled Python sidecar

## Quick start

```bash
npm install
python -m pip install -r backend/requirements.txt

# Terminal A
python backend/app.py

# Terminal B
npm run dev
```

Open <http://localhost:5173>. On first launch, paste the contents of `browser.json` or use the OAuth flow. Credentials and statistics are stored outside the repository. Do not commit session data.

## Tauri packaging

```bash
# Generate icons when needed
node scripts/generate-tauri-icons.mjs

# Build a target-specific sidecar (requires PyInstaller)
python scripts/build_sidecar.py

# Development desktop shell
npm run tauri dev

# Release bundles
npm run tauri build
```

`src-tauri/tauri.conf.json` disables native decorations, points Tauri at the Vite frontend, declares `binaries/ytm-backend` as an external binary, and includes the backend resource. `src-tauri/src/lib.rs` first attempts the sidecar and then falls back to `python backend/app.py` in a source checkout. The Windows installer workflow is under `.github/workflows/`; inspect the audit before relying on it for a release because multiple workflow drafts currently use different sidecar names and targets.

## Configuration

| Variable | Default | Used by | Purpose |
| --- | --- | --- | --- |
| `YTM_BIND_HOST` | `127.0.0.1` | `backend/app.py` | Flask bind address. Use `0.0.0.0` only on a trusted LAN/VPN for the mobile remote. |
| `YTM_BACKEND_PORT` | `5178` | Flask, Tauri launcher, invite URL | Local backend port. Keep it private when credentials are loaded. |
| `YTM_CORS_ORIGINS` | empty | `backend/app.py` | Comma-separated additional allowed origins. The app adds its local frontend/Tauri origins. |
| `YTM_DATA_DIR` | platform user config directory | `backend/app.py` | Override the directory for `browser.json`, `oauth.json`, `stats.db`, settings, library cache, and audio cache. |
| `PYTHONUNBUFFERED` | unset | Tauri sidecar launcher | Set to `1` by the Rust shell for readable sidecar logs. |

`PARTY_RELAY_URL` is not currently consumed by the runtime; the relay source is a separate deployment draft and should not be documented as an active configuration path until hybrid routing is wired.

## Data and privacy

- Windows default: `%APPDATA%\\ytm-player\\`
- macOS/Linux default: `~/.config/ytm-player/`
- `browser.json` / `oauth.json`: YouTube session credentials
- `stats.db`: listening events, features, palettes, and persisted resolver offsets
- `audio_cache/`: local LRU-capped media cache; the default cap is 1 GiB
- `settings.json`: quality and cache settings

The backend defaults to `127.0.0.1`, applies input validation and rate limits, and restricts CORS origins. LAN mode exposes authenticated endpoints to the local network, so use a trusted network and narrow `YTM_CORS_ORIGINS`.

## Repository map

```text
backend/app.py                 Flask routes, provider adapters, SQLite setup, streams
backend/lyrics_yrc.py          Low-memory YRC ingestion and cadence fallback
backend/party.py               In-memory Party Mode room/state engine
backend/radio.py               Radio payload normalization and duplicate policy
src/App.svelte                 Application state owner and shell composition
src/lib/audio.js               Dual media decks, Web Audio, crossfade, analyser
src/lib/queue.js               Queue state transitions and local persistence
src/lib/mix.js                 Cancellable radio requests and deduplication
src/lib/lyrics.js               Lyrics metadata and video-offset transformations
src/lib/cadence_engine.js      Browser-side model-free cadence fallback
src/pages/TheatreMode.svelte   Theatre stage, lyrics, queue drawer, video mode
src/components/KaraokeLyrics.svelte  rAF-driven syllable rendering
src-tauri/src/lib.rs           Tauri process, tray, and window-state lifecycle
party-relay/                   Cloudflare Durable Object relay draft
scripts/build_sidecar.py       PyInstaller sidecar helper
```

## Verification

The package defines only `dev`, `build`, `preview`, and `tauri`; it does not define a JavaScript linter or test script. The minimum local checks are:

```bash
npm run build
python -m py_compile backend/app.py backend/lyrics_yrc.py
node --check party-relay/worker.js
git diff --check
```

For provider-dependent behavior, use isolated Flask test-client probes with mocked ytmusicapi/yt-dlp responses. Never use real account mutation calls as a build test.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a change. Security and architecture findings are tracked in [AUDIT_AND_RECOMMENDATIONS.md](AUDIT_AND_RECOMMENDATIONS.md). Release history is in [CHANGELOG.md](CHANGELOG.md).

## License

No project license has been declared yet. Treat the repository as all-rights-reserved until a license is added.
