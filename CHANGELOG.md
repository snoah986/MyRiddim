# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use [Semantic Versioning](https://semver.org/).

## [Unreleased]

> These entries describe work currently present in the checkout but not yet committed. Validate and split this work before release.

### Added

- First-pass Party Mode host engine with in-memory rooms, guest roles, request quotas, cooldowns, approvals, voting, LAN invite links, and mobile guest UI.
- Cloudflare Durable Object relay source under `party-relay/`.
- YouTube Music multi-shelf home feed, Home/Discover navigation, related-artist discovery, and a 60/40 discovery-oriented recommendation path.
- Explicit Start Mix controls on playable shelves and queue recommendations.
- Theatre Mode queue drawer with history, active-track styling, drag reorder, recommended injection, playlist save toast, playlist target switching, and hold-to-clear for manually queued tracks.
- Persistent video-resolution and intro-offset tables, LRCLIB-first lyrics, video offset waterfall, YRC ingestion, and low-memory cadence fallback.
- Syllable-level karaoke rendering with direct CSS-property updates from `requestAnimationFrame`.
- Audio deck race protection, crossfade handoff logic, native video resolution fallbacks, and stream caching.
- Tauri window controls, window-state plugin wiring, tray menu, sidecar build script, and release workflow drafts.

### Changed

- Frontend metadata normalization now rejects unusable placeholder rows before they reach shelves, queues, mixes, or playback.
- Theatre Mode was rebuilt around an editorial visual stage, responsive video/art presentation, synced lyrics, queue drawer, and cinema fade.
- Queue and playback state now persist locally and are owned by `src/lib/queue.js` and `App.svelte` rather than by individual shelves.
- Backend runtime data and credentials are moved outside the repository into the platform user-data directory.

### Fixed

- Stream and video resolver ladders now use strict direct YouTube URLs and retain progressive MP4/WebM fallbacks.
- Stale recommendation and stream requests are rejected when a newer track/request wins.
- Manual queue flushing preserves radio backfill.
- Companion video lookups cache positive and negative resolutions by source track.

### Under the Hood

- This checkout has no configured JavaScript, Python, or Markdown linter in `package.json`.
- The working tree contains a large mixed uncommitted feature set, including a deleted legacy sidecar binary and a replacement untracked binary; this is not a release artifact.
- The current history ends at three commits; the feature list above is not yet represented in a release commit.

## [1.2.0] - 2026-09-03

### Added

- Tauri 2 desktop shell with frameless window configuration, custom window controls, tray support, and window-state plugin.
- Flask/ytmusicapi bridge with browser-session authentication, local listening statistics, playlist operations, stream proxying, cache support, PWA assets, and synced lyrics.
- Svelte player UI with Theatre Mode, queue handling, crossfade audio engine, Media Session actions, search, playlists, and statistics.
- GitHub Actions desktop build workflow and target-specific Tauri assets.

### Changed

- Backend defaults to localhost and validates YouTube, playlist, browse, and canonical IDs.
- Runtime credentials and statistics are intended to live outside the project tree.

### Fixed

- Added cache and proxy paths intended to avoid repeated stream resolution and support seeking.

### Under the Hood

- Initial public application baseline for the local-first player.

## [0.1.0] - 2026-09-03

### Added

- Initial prototype baseline, reconstructed from the first repository snapshot represented by the initial release commit.

[Unreleased]: https://github.com/snoah986/MyRiddim/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/snoah986/MyRiddim/releases/tag/v1.2.0
