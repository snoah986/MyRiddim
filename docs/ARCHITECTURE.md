# Architecture and Dependency Boundaries

## Runtime shape

```text
Svelte 5 + Vite
  ├── @sveltejs/vite-plugin-svelte
  ├── qrcode
  ├── @tauri-apps/api and Tauri plugins
  └── src/lib/audio.js, queue.js, mix.js, lyrics.js
          │ same-origin HTTP
          ▼
Flask sidecar
  ├── Flask + flask-cors
  ├── ytmusicapi and yt-dlp
  ├── requests and rapidfuzz
  ├── SQLite listening history and cache
  └── lyrics, stream, recommendations, Party, and remote routes
          │ outbound provider calls
          ├── YouTube Music
          ├── YouTube / yt-dlp
          ├── LRCLIB
          ├── NetEase YRC fallback
          └── optional SponsorBlock / Cloudflare tunnel paths
```

The optional Rust/Tauri shell starts and owns the Python sidecar, window/tray lifecycle, single-instance behavior, updater, and process cleanup. The frontend owns visible playback and navigation state. `src/lib/queue.js` owns queue transitions and `src/lib/audio.js` owns the dual media decks. The backend owns provider access, credentials, SQLite schema, normalization, stream resolution, lyrics, and cache policy.

## Dependency inventory

- **Node runtime:** Svelte 5, Vite 8, the Svelte Vite plugin, and local QRCode rendering.
- **Tauri frontend/runtime:** Tauri API, process, updater, and CLI packages.
- **Python runtime:** Flask, CORS, ytmusicapi, yt-dlp, rapidfuzz, and requests.
- **Rust runtime:** Tauri 2, shell/window-state/updater/process/single-instance plugins, serde, and serde_json.
- **Transitive dependencies:** npm and Cargo lockfiles are committed. Python currently has no lockfile and is the main reproducibility gap.

## Third-party integration boundaries

Provider calls must remain behind backend adapters and normalized response contracts. Rendering components must not receive raw provider payloads. Credential and history paths must remain in the platform user-data directory. Network-facing features such as Party relay, public tunnels, and LAN remote require separate authorization and rate-limit review before production exposure.

## Update boundaries

- Update frontend packages with frontend build and browser smoke checks.
- Update Python/provider packages with mocked Flask route probes, provider fallback checks, and Python compilation.
- Update Rust/Tauri packages with locked Cargo checks, sidecar packaging, and process lifecycle checks.
- Update GitHub Actions separately from runtime dependencies.

See `docs/DEPENDENCY_AUDIT.md` for the current evidence and queue, and `docs/REFACTORING_PLAN.md` for major upgrade handling.
