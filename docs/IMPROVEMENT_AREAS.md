# Dependency Improvement Areas

## Current gaps

1. **Python reproducibility:** `backend/requirements.txt` contains unpinned packages and no lock or constraints file.
2. **Scanner coverage:** npm audit is available locally; Python and Rust scanners now run in CI but were not available in the local workstation audit.
3. **Workflow drift:** build workflows use different Node and Python versions, install commands, and sidecar packaging paths.
4. **Release confidence:** the repository has no JavaScript test or lint script, and provider-dependent behavior lacks a repeatable integration test contract.
5. **License evidence:** the package manifest and README disagree about whether the project license is declared, and no transitive license inventory is checked in.
6. **Dependency graph size:** the Flask provider bridge, yt-dlp, YouTube Music client, Web Audio/Tauri UI, and Rust shell cross several independently failing surfaces.

## Optimization opportunities

- Generate and review a Python constraints file for the supported Python version.
- Standardize on `npm ci`, `cargo check --locked`, and one supported CI runtime baseline.
- Add a license inventory job after choosing an approved output format.
- Add deterministic Flask route tests with fake provider clients before batching provider-library updates.
- Add browser smoke coverage for playback, Theatre, queue, lyrics seek, search, and Tauri fallback behavior.
- Keep dev-only tooling separate from production runtime updates.
- Review large or optional packages for startup, bundle, and native sidecar impact before replacing them.

## Maintenance signals to track

- time from advisory publication to fixed deployment;
- number of open Dependabot PRs and stale updates;
- failed update PRs by ecosystem and package;
- rollback frequency;
- bundle size and startup regressions;
- transitive package count and license exceptions.

These metrics should inform replacement decisions rather than package popularity alone.
