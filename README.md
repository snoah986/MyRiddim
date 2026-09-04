# ytm-player — Local YouTube Music player

A local-first YouTube Music player: a Svelte frontend + a Flask backend that bridges
the [ytmusicapi](https://github.com/tjws/ytmusicapi) library, with Theatre Mode,
synced lyrics, gapless crossfade, a Web Audio visualizer, PWA support, and a
Tauri desktop shell. **Everything runs on your machine** — no cloud, no accounts
except your own YouTube Music session.

> ⚠️ **Security**: the backend holds your real Google session cookies. It binds to
> `127.0.0.1` only, validates all IDs, and rate-limits YouTube calls. Never expose
> port `5178` to the network, and never commit `browser.json`.

---

## 1. Authentication (required)

The app needs your YouTube Music session. Paste the contents of a
[ytmusicapi](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html)
`browser.json` (or raw copied request headers) into the setup screen the first
time you launch. It is stored **outside the project tree** in the user data
directory — `%APPDATA%\ytm-player\browser.json` on Windows,
`~/.config/ytm-player/browser.json` on macOS/Linux (set `YTM_DATA_DIR` to
override) — so the repo can never leak your session. Same for `oauth.json`.
The backend migrates any legacy in-repo copies automatically on first launch.

If your session expires, the UI shows a "Session expired" banner — click
**Re-authenticate in Settings**, then paste fresh credentials.

## 2. Run as a local web app (no build tools needed)

Prerequisites: Node.js ≥ 18 and Python ≥ 3.10.

```bash
# 1. Frontend dependencies
npm install

# 2. Python backend dependencies
pip install -r backend/requirements.txt   # flask, flask-cors, ytmusicapi, yt-dlp

# 3. Terminal A — backend (port 5178)
python backend/app.py

# 4. Terminal B — frontend dev server (port 5173)
npm run dev
```

Open http://localhost:5173, paste your `browser.json`, and you're in.

### iPhone remote (optional LAN mode)

The Flask backend serves a standalone, installable remote at `/mobile`. It is
localhost-only by default. To use it from an iPhone on a trusted home network:

```bash
# Windows PowerShell
$env:YTM_BIND_HOST = "0.0.0.0"
$env:YTM_CORS_ORIGINS = "http://192.168.1.45:5178"
python backend/app.py
```

Replace `192.168.1.45` with the computer's LAN address, then open
`http://192.168.1.45:5178/mobile` in Safari and choose **Share → Add to Home
Screen**. The remote polls the desktop's live playback state and sends validated
play, seek, volume, shuffle, repeat, previous, next, queue, search, and lyrics
commands. Keep this on a trusted LAN or VPN only: exposing the backend publicly
would expose the authenticated music session.

`yt-dlp` resolves audio streams (standalone, unmerged formats — no `ffmpeg` needed).
Optional extras: `js_engine` falls back to Node for signature challenges (Node is
already present).

## 3. Build & run as a Tauri desktop app

Prerequisites: Rust toolchain + MSVC Build Tools (Windows), Node ≥ 18, Python ≥ 3.10.

```bash
# 1. Rust + MSVC
#    - install https://rustup.rs
#    - install "Desktop development with C++" via Visual Studio Installer

# 2. JS dependencies (includes @tauri-apps/cli and @tauri-apps/api)
npm install

# 3. Generate app icons
node scripts/generate-tauri-icons.mjs

# 4. Package the Python backend as a sidecar (optional; without it the app
#    falls back to launching `python backend/app.py` from the project dir)
#    pip install pyinstaller -r backend/requirements.txt
#    pyinstaller --onefile --name ytm-backend backend/app.py
#    cp dist/ytm-backend(.exe) src-tauri/binaries/ytm-backend-<TARGET-TRIPLE>
#    (Tauri requires the target-triple suffix, e.g. ytm-backend-x86_64-pc-windows-msvc.exe)

# 5. Dev run (Tauri starts Vite and the Python fallback automatically)
npm run tauri dev

# 6. Release build → src-tauri/target/release/bundle/
npm run tauri build
```

### How the desktop shell works

- `src-tauri/tauri.conf.json` — window (1200×800, frameless with custom controls),
  frontend build, and sidecar (`externalBin: ytm-backend`) wiring.
- `src-tauri/src/lib.rs` — on startup, spawns the backend: first the bundled
  sidecar binary, falling back to `python backend/app.py`; passes the fixed local
  port and app-data directory; kills it on restart and application exit.
- `src/components/WindowControls.svelte` — minimize / maximize / close buttons in
  the header; rendered only inside the Tauri window (browser builds ignore them).
- Media keys (Play/Pause/Next/Previous) work via the browser **Media Session API**
  — available in both the web and desktop shells. Windows taskbar controls still
  require a native media-session integration and are not claimed as implemented.

## 4. Project layout

```
backend/app.py            Flask bridge and HTTP adapters (auth, playlists, search, streams, lyrics, stats, cache)
backend/radio.py          Pure radio-response normalization and duplicate policy
src/                      Svelte 5 frontend
  App.svelte              UI state owner: current track, queue connection, toasts, and view routing
  lib/tracks.js           Pure playable-track identity normalization
  lib/mix.js              Radio request engine: cancellation, stale-response guards, normalization, deduplication
  lib/queue.js            Queue store and queue transitions (persisted to localStorage)
  lib/audio.js            Web Audio engine: crossfade, visualizer, normalization
  lib/settings.js         Settings store (persisted to localStorage)
  components/             Rendering-only controls and shelves, including StartMixButton and TrackContextMenu
  pages/                  Entity and player views (SongPage, ArtistPage, AlbumPage, TheatreMode)
src-tauri/                Tauri 2 desktop shell + sidecar contract
public/                   PWA manifest, service worker, icons
```

### State ownership and data flow

`App.svelte` owns user-visible application state and passes callbacks down to
rendering components. Components emit intent; `App.svelte` delegates pure track
policy to `lib/tracks.js`, asynchronous radio work to `lib/mix.js`, and queue
transitions to `lib/queue.js`. The backend owns provider access and HTTP
contracts; `backend/radio.py` normalizes provider payloads before the route
returns them. Data flows upward as callbacks/events and downward as props, with
no component owning a second copy of queue or playback state.

## 5. Data & privacy

- `browser.json` / `oauth.json` — your YouTube session credentials, kept
  **outside the repo** in the user data directory (see §1). Never inside the tree.
- `stats.db` — listening history used for the Monthly Recap / Heavy Rotation
  shelves; exportable as JSON from Settings. Also stored outside the repo in the
  user data directory.
- `.freebuff/audio_cache/` — LRU-capped (default 1 GB, configurable in Settings)
  cache of recently played audio so repeat plays skip yt-dlp. Git-ignored.