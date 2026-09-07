# Dependency Refactoring and Major Upgrade Plan

## Operating rule

Upgrade one major dependency at a time. Do not combine a major dependency update with a feature redesign, packaging rename, or database migration unless the migration is required by the dependency.

## Phases

### Phase 0: baseline

- Capture the current manifest and lockfile hashes.
- Run `npm ci`, `npm run build`, Python compilation, and `cargo check --locked`.
- Record runtime versions and the critical flows exercised.
- Confirm no credentials, caches, generated binaries, or databases are in the change.

### Phase 1: Python lock and scanner baseline

- Choose a supported Python version range.
- Generate a reviewed constraints or lock file from `backend/requirements.txt`.
- Run `pip-audit` against the locked resolution.
- Update the backend installation and CI to consume the same resolution.
- Preserve a documented command to refresh it.

### Phase 2: frontend and tooling majors

For Svelte, Vite, QRCode, Tauri JavaScript packages, or the Node runtime:

1. Read the official migration guide and changelog.
2. Search all imports, plugin configuration, build scripts, and generated artifacts.
3. Upgrade only the selected package and lockfile.
4. Run the dependency workflow and inspect warnings, bundle size, and browser behavior.
5. Exercise playback, search, Theatre, lyrics seeking, queue, and responsive layouts.
6. Record removed APIs and replacements in the PR.

### Phase 3: backend/provider majors

For Flask, ytmusicapi, yt-dlp, requests, or rapidfuzz:

1. Mock provider responses and test normalization, stream resolution, lyrics fallback, and error paths.
2. Verify cookies and extractor arguments are still passed as intended.
3. Check timeouts, retries, rate limits, SQLite migrations, and cache behavior.
4. Run the backend import and compilation checks.
5. Validate the Tauri sidecar against a clean checkout if packaging code is affected.

### Phase 4: Rust/Tauri majors

For Tauri or plugin majors:

1. Read the plugin migration notes and capability changes.
2. Run `cargo check --locked` and a target build.
3. Exercise single-instance behavior, sidecar startup, RAII cleanup, tray actions, updater permissions, and window state.
4. Confirm externalBin target names on every supported platform.

## Breaking-change record

Every major update must include:

```text
Dependency and old/new versions:
Why the update is needed:
Breaking APIs or behavior:
Affected files/imports:
Migration or codemod:
Tests and real flows exercised:
Bundle/startup impact:
Rollback commit and version:
Owner and follow-up date:
```

## Safe rollback

- Revert the dependency commit while preserving unrelated fixes.
- Restore the previous lockfile and reinstall with the ecosystem's lock-respecting command.
- Re-run the baseline commands and dependency scanners.
- If the package must remain updated for security, pin the compatible fixed release and open a follow-up migration item.

No major version is considered complete until the migration record and rollback path are reviewed.
