# Engineering Audit & Recommendations

**Audit date:** 2026-09-04  
**Scope:** repository tree, committed history, current uncommitted checkout, configuration, and source inspection.  
**Method:** read-only inspection plus the project’s available build/compile checks. No runtime code was changed during this documentation pass.

## Executive assessment

**Health score: 5.2 / 10**

The project has a credible local-player foundation and several good boundaries: provider access stays in Flask, queue transitions are isolated in `src/lib/queue.js`, radio cancellation lives in `src/lib/mix.js`, credentials are moved outside the repository, and the Tauri shell owns backend process cleanup. The main risk is delivery coherence, not a missing demo feature: the working tree combines desktop packaging, Party Mode, discovery, stream/lyrics fixes, queue redesign, and karaoke work in one uncommitted set while the largest runtime files remain monoliths.

## Repository and history

The repository currently has three commits on `main`, with `origin/main` pointing at the same HEAD:

1. `3fca309` — Tauri desktop shell, security hardening, and initial CI packaging (`v1.2.0`)
2. `3633f0d` — additional GitHub Actions build workflow
3. `e22cfe0` — cloud build workflow and broad backend/frontend expansion

The checkout has 13 modified/deleted tracked paths and multiple untracked additions, including Party Mode, layouts, lyric/karaoke modules, release workflow drafts, a replacement Windows sidecar binary, and a deleted legacy sidecar binary. The current working tree is not a clean release candidate.

## Immediate technical debt

### P0 — release and correctness blockers

1. **Sidecar naming and workflow drift.** `src-tauri/tauri.conf.json` declares `binaries/ytm-backend`, while `.github/workflows/build.yml` builds/copies `backend-x86_64-pc-windows-msvc.exe`. `.github/workflows/tauri.yml` and `scripts/build_sidecar.py` use different naming and packaging strategies. A clean CI build must prove the exact binary name, target triple, and executable layout consumed by Tauri.
2. **No automated test/lint contract.** `package.json` has no `test`, `check`, `lint`, or `format` script. Provider-dependent routes and dual-deck handoff therefore have no repeatable CI regression suite. Add deterministic tests before merging more behavior.
3. **Large mixed uncommitted change set.** Backend, UI redesign, Party Mode, packaging, binaries, and karaoke are entangled. Review, rollback, and bisectability are poor. Split at least into packaging, backend contracts, playback/queue, Theatre UI, Party Mode, and documentation.
4. **Bundled binary provenance.** A generated Windows executable is deleted and another is untracked. Do not commit opaque binaries until the build is reproducible and the artifact is intentionally tracked or moved to release storage.

### P1 — architecture and operational risks

1. **`backend/app.py` is 3,755 lines.** Routing, authentication, database migrations, stream proxying, lyrics, recommendations, party adapters, and provider policy share one module. A migration or provider change requires reading a large cross-cutting file.
2. **`src/App.svelte` is 1,202 lines and `TheatreMode.svelte` is 1,020 lines.** App state, async fetching, media session, keyboard handling, layout selection, queue markup, party controls, lyrics timing, and video controls are spread across two large components. This conflicts with the intended one-owner architecture even where the code has helper modules.
3. **Duplicated queue UI.** `App.svelte` still contains a legacy queue drawer while `TheatreMode.svelte` contains the redesigned queue drawer. Both expose queue tabs, row actions, and recommendations. This is a concrete source of behavior drift.
4. **Provider normalization is not universal.** `normalize_track()` protects many catalog paths, but raw fallback data still appears in persisted/statistics paths and the live preview showed `Unknown Artist`/`Unknown title` rows in existing shelves. Migration/backfill must sanitize stored data, not only new responses.

### P2 — performance and product polish

1. **Animation ownership is split.** `src/lib/audio.js`, `TheatreMode.svelte`, `App.svelte`, and `KaraokeLyrics.svelte` each own timers or animation loops. The karaoke component avoids Svelte updates per frame, but the Theatre visualizer and lyric loop need explicit mount/unmount profiling when switching modes.
2. **Network work is best-effort but broad.** Home startup launches playlists, discovery, smart playlists, liked tracks, favorite artists, and extras in parallel. Add request cancellation, cache freshness metadata, and bounded concurrency for a predictable handheld experience.
3. **Artwork sampling and blur are GPU-sensitive.** Canvas sampling is small, but Theatre mesh orbs, blur filters, backdrop video, grain, and CSS transitions can be expensive on Legion Go/Steam Deck battery profiles. Provide a reduced-effects preset and measure frame time at 60 Hz.
4. **No measurable RAM budget.** The low-RAM karaoke path avoids Whisper/Torch and uses small arrays, but the repository does not yet report process/webview RSS or prove the `<5 MB` incremental target. Measure it rather than claiming it.

## Tauri / Rust layer

### What is sound

- `src-tauri/src/lib.rs` owns the backend child and kills both sidecar and Python fallback processes on exit.
- The shell uses `tauri-plugin-window-state` and configures a frameless window.
- The tray handle is retained for the application lifetime, and tray actions emit frontend events for playback.
- Backend data is redirected to the Tauri app data directory when available.

### Gaps

- No inspected Rust test covers sidecar spawn failure, restart, process cleanup, or tray events.
- `python_script()` uses current working directory before resource directory; a packaged app launched from an unexpected working directory must be tested with the sidecar absent.
- The frontend fallback port and health response still contain fixed `5178` assumptions even though the launcher accepts `YTM_BACKEND_PORT`.
- Window state is plugin-enabled, but there is no acceptance test proving dimensions, position, and maximized state survive a relaunch.
- “Taskbar thumbnail controls” and OS-native SMTC/MPRIS are not implemented; Media Session API is the current cross-platform approximation.

## Backend / Flask layer

### Strengths

- Default bind is localhost; LAN mode is opt-in.
- Input IDs are validated before provider or filesystem use.
- Stream proxy routes support range requests and reject non-media URLs.
- Credential writes are atomic and stored outside the repository.
- Rate limits exist on several expensive routes.
- SQLite initialization includes additive migrations and indexes.

### Gaps

- `health()` reports a fixed `port: 5178` even when `YTM_BACKEND_PORT` changes.
- CORS origins include fixed local ports and an environment extension, but LAN authentication is not independently enforced; binding to `0.0.0.0` exposes powerful endpoints to every trusted-LAN client.
- `PARTY_STORE` is process-local. Multiple workers, restarts, or a sidecar restart lose rooms; the relay draft is not wired into the host/mobile runtime.
- `video_offsets` persistence is durable, but resolver calls depend on external SponsorBlock, yt-dlp, and optional transcript behavior without a circuit breaker or provider telemetry.
- Some legacy listen/stat paths still intentionally insert placeholder metadata. This can reintroduce “Unknown title/artist” despite catalog normalization.
- The application imports `requests` only in the new YRC helper, so deployment correctness depends on the requirements file staying synchronized; there is no dependency lock for Python.

## Frontend / Svelte layer

### Strengths

- Queue transitions are centralized in `src/lib/queue.js`.
- Radio requests have abort and stale-response guards in `src/lib/mix.js`.
- `KaraokeLyrics.svelte` directly mutates line/word CSS properties from rAF rather than setting Svelte state every frame.
- Components expose keyboard-accessible buttons and use explicit callbacks for most mutations.
- The frontend has real responsive shells and a native drag/drop entry point.

### Gaps

- `App.svelte` still owns too many concerns: authentication, route selection, player lifecycle, stream fetching, party polling, recommendations, persistence, media session, global key handling, and legacy queue markup.
- `TheatreMode.svelte` still owns queue presentation, recommendation fetching, playlist save flow, video mode, lyric offset logic, visualizer, party host UI, and stage rendering. Extracting a `QueueDrawer` and a `useTheatreSync`-style module would improve testability without adding a state framework.
- Existing Vite output reports accessibility and unused-selector warnings in `App.svelte`, `HomeView.svelte`, `SettingsModal.svelte`, `SmartPlaylistModal.svelte`, `SongPage.svelte`, and `SidebarLayout.svelte`. They are not fatal, but they should not be normalized as release noise.
- The preview has shown real rows with placeholder metadata, and live preview/HMR can become stale after syntax errors. A clean browser smoke suite is needed after each large component change.
- There are no frontend unit tests for crossfade handoff, media errors, lyric seek, queue drawer dismissal, or Start Mix.

## Security and network hygiene

- Keep `YTM_BIND_HOST=127.0.0.1` by default.
- Treat `YTM_BIND_HOST=0.0.0.0` as a privileged mode: add an explicit LAN-mode warning, a per-session capability token for remote mutations, and origin-independent authentication before recommending it broadly.
- Avoid putting credentials or raw provider URLs in logs. Current logs include IDs and exception text; review production log retention before shipping.
- Party room IDs use `secrets.token_hex`, which is appropriate as an identifier, but the relay currently accepts a room code as the principal. Add signed guest capabilities, expiry, and host authorization before public deployment.
- The QR code is generated through `api.qrserver.com`, an external third party. This leaks the invite URL; either make it opt-in and clearly disclose it or generate QR locally with a maintained dependency.
- The Cloudflare worker accepts WebSockets but has no authentication, rate limiting, persistence, or replay protection beyond message-size/connection limits. It is a draft, not a production relay.

## Packaging and CI findings

- There are three workflow files with overlapping build/release responsibilities and one tracked nested path `.github/workflows/.github/workflows/build.yml` that GitHub will not treat as a normal workflow.
- The workflows disagree on Node/Python versions, sidecar names, target matrices, and whether builds are releases or artifacts.
- The release workflow sets empty Tauri signing variables. Unsigned builds may be acceptable for development, but a public Windows release needs signing policy and documented secrets.
- The configured bundle targets include `nsis`, `app`, and `dmg`, but the release workflow is Windows-only and assumes an `.exe` inside the `app` bundle. Verify the actual Tauri output before publishing.
- CI runs `npm install` in some workflows and `npm ci` in another; standardize on lockfile-respecting installs.

## Ranked action plan

### P0 — before merge or release

1. Split the working tree into reviewable commits and remove generated/runtime artifacts from the feature commits.
2. Consolidate CI into one validated build workflow plus one tag release workflow; fix the sidecar name/target-triple contract.
3. Add Python route tests with fake provider clients and browser tests for play, queue, Theatre, lyrics, and video failures.
4. Run a clean packaged Windows build from a fresh checkout with no system Python available.

### P1 — next engineering pass

1. Move stream/lyrics/video-offset code into backend modules with explicit service interfaces.
2. Extract `QueueDrawer.svelte`, `TheatreSync` helpers, and the app-level data loaders from `App.svelte`.
3. Remove the duplicate queue drawer from `App.svelte` after the Theatre drawer is the single surface.
4. Add a provider/cache observability panel: resolver latency, cache hit rate, fallback tier, and error class.

### P2 — performance and security

1. Profile WebView RSS, GPU frame time, and audio latency on Windows handheld and Linux desktop targets.
2. Add authenticated LAN remote capabilities and local QR generation.
3. Add schema migrations that scrub placeholder metadata and enforce usable title/artist fields at ingestion.
4. Bound startup fetch concurrency and add freshness-aware local cache hydration.

### P3 — product completeness

1. Implement native SMTC/MPRIS/taskbar integration rather than relying solely on Media Session.
2. Add offline-aware provider queues and retry/backoff.
3. Add release signing, update strategy, and a support/diagnostics export.

## Verification status for this audit

- `npm run build`: passed during the current feature pass; emits known Svelte accessibility/unused-selector warnings.
- Python compilation: passed for the backend modules exercised during the current feature pass.
- `git diff --check`: passed; Git reports line-ending normalization warnings only.
- JavaScript tests/lint: no repository-defined test or lint command exists.
- Full Tauri packaging: not proven in this audit; CI/workflow drift is a release blocker.
