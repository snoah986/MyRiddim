# Contributing

Thanks for helping with Freebuff Desktop / myriddim. The project is local-first and handles real YouTube session credentials, so correctness and privacy matter more than shipping a broad speculative diff.

## Before you start

1. Create a branch from `main`.
2. Do not copy `browser.json`, `oauth.json`, `stats.db`, audio cache files, or private invite data into a commit.
3. Read [AUDIT_AND_RECOMMENDATIONS.md](AUDIT_AND_RECOMMENDATIONS.md) for current architecture and release blockers.
4. Keep unrelated feature work out of the same commit.

## Local setup

```bash
npm install
python -m pip install -r backend/requirements.txt
```

Run the app in two terminals:

```bash
python backend/app.py
npm run dev
```

Use the setup screen for authentication. Never paste credentials into issues, logs, screenshots, or test fixtures.

## Validation

The repository currently defines no test or lint script in `package.json`. Run the available checks before opening a change:

```bash
npm run build
python -m py_compile backend/app.py backend/lyrics_yrc.py
node --check party-relay/worker.js
git diff --check
```

For backend routes that call YouTube, LRCLIB, NetEase, SponsorBlock, or yt-dlp, add deterministic Flask test-client probes with mocked provider responses. Do not use a real account mutation as a test. For frontend behavior, exercise the real Preview/dev surface when possible: play a track, open Theatre, open/close Queue, seek lyrics, trigger Start Mix, and verify stale requests cannot replace newer state.

## Change boundaries

Prefer one concern per commit:

- Tauri packaging / CI / sidecar naming
- Backend provider or SQLite contract
- Audio engine / queue behavior
- Theatre and queue presentation
- Party Mode / relay
- Documentation

Do not commit generated `dist/`, `target/`, PyInstaller work directories, local caches, or opaque binaries unless the release process explicitly requires a reviewed artifact.

## Code conventions

- Match the existing JavaScript/Svelte style: small functions, explicit callbacks, and no new state framework without a demonstrated need.
- Keep provider/network logic out of rendering components.
- Use `src/lib/queue.js` for queue transitions and `src/lib/audio.js` for media-deck operations.
- Normalize provider metadata at the backend boundary and reject unusable IDs/titles before rendering or queueing.
- Cancel or invalidate stale asynchronous requests when the selected track changes.
- Clean up `setInterval`, `setTimeout`, `requestAnimationFrame`, event listeners, and media resources on component teardown.
- Keep local data paths outside the project tree and preserve the localhost-safe default.
- Use tabular monospace formatting for durations, offsets, and timecodes.

## Documentation

Update `README.md` when setup, configuration, packaging, or architecture changes. Add user-visible behavior to `CHANGELOG.md` under `[Unreleased]`. Record known limitations honestly rather than presenting drafts—especially Party relay, native SMTC/MPRIS, and release signing—as production features.

## Pull requests

A good PR description includes:

- user-visible outcome and motivation;
- files/areas changed;
- commands run and their results;
- provider-dependent checks that were mocked versus exercised live;
- screenshots or a short recording for UI changes;
- known warnings, regressions, and follow-up work.

Keep PRs reviewable. If a feature requires a broad migration, submit the safe structural preparation separately from the behavior change.

## Security reports

Do not publish credentials, raw YouTube request headers, stream URLs, or LAN invite tokens in a public issue. Contact the repository owner privately and include reproduction steps with secrets removed.
