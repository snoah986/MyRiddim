# Dependency Audit and Update Plan

**Audit date:** 2026-09-06  
**Scope:** manifests, lockfiles, CI workflows, and local dependency tooling.  
**Policy:** do not upgrade a dependency in this report without a separate reviewed update change.

## Detected ecosystems

| Ecosystem | Evidence | Lock status | Current handling |
| --- | --- | --- | --- |
| npm | `package.json`, `package-lock.json` | Lockfile present | Dependabot and CI audit |
| Python | `backend/requirements.txt` | No Python lockfile | Dependabot and `pip-audit` in CI |
| Rust | `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock` | Lockfile present | Dependabot and `cargo audit` in CI |
| GitHub Actions | `.github/workflows/*.yml` | Action refs are version tags | Dependabot weekly updates |
| Java, Go, Ruby, PHP | No manifest detected | Not applicable | No automation added |

No monorepo workspace or package-manager workspace was detected.

## Dependency tree

```text
Frontend / build
├── @sveltejs/vite-plugin-svelte 7.3.0
├── svelte 5.57.0
├── vite 8.2.2
├── qrcode 1.5.4
├── @tauri-apps/api 2.11.1
├── @tauri-apps/plugin-process 2.3.1
├── @tauri-apps/plugin-updater 2.11.0
└── @tauri-apps/cli 2.11.4 [development]
│
├── package-lock.json transitive graph
└── npm registry / Vite build

Python backend
├── flask
├── flask-cors
├── ytmusicapi
├── yt-dlp
├── rapidfuzz
└── requests
│
└── No Python lockfile currently pins the resolved transitive graph

Tauri shell
├── tauri 2
├── tauri-plugin-shell 2
├── tauri-plugin-window-state 2
├── tauri-plugin-updater 2
├── tauri-plugin-process 2
├── tauri-plugin-single-instance 2
├── serde 1
└── serde_json 1
    └── Cargo.lock pins transitive crates
```

The npm inventory above is the installed direct tree from `npm ls --depth=0`. The Rust manifest uses major-version ranges while `Cargo.lock` supplies the resolved graph. Python requirements are unpinned and therefore need a lock strategy before reproducible production packaging can be claimed.

## Security and outdated results

The following commands were run in the checkout:

```text
npm audit --audit-level=high  -> 0 vulnerabilities
npm outdated --long           -> no rows returned
npm ls --all --depth=0        -> direct installed versions listed above
```

No Critical or High npm vulnerability was reported. No CVE with a CVSS score is claimed for Python or Rust from the local run because `pip-audit` and `cargo-audit` were not installed in the workstation environment. CI now runs both scanners, and a failing scanner is a release blocker.

No deprecation or license conclusion can be made from these commands alone. The repository manifest declares `ISC`, while the README currently says that no project license has been declared. Resolve that contradiction and generate a transitive license inventory before publishing a compliance assertion.

## Prioritized queue

### P0: security and reproducibility

1. Run the new Python and Rust audits in CI and remediate every Critical or High finding before merge.
2. Add a Python lockfile or constraints file generated from the supported Python version and update `CONTRIBUTING.md` with the refresh procedure.
3. Resolve the project-license contradiction and add a license inventory for npm, Python, and Rust transitive dependencies.
4. Standardize CI on `npm ci` and one supported Node/Python version matrix. Existing workflows currently mix `npm install`, Node 20/22, and Python 3.11/3.12.

### High risk: major updates

No major npm update was returned by `npm outdated` during this audit. Major updates to Tauri, Svelte, Vite, Flask, ytmusicapi, or yt-dlp remain one-at-a-time changes because they cross the frontend, sidecar, provider, or packaging boundaries.

For each major update: read the upstream migration guide, branch separately, update one ecosystem, run the dependency workflow, run the packaged Tauri check where applicable, and record import/API changes in `docs/REFACTORING_PLAN.md`.

### Medium: minor updates

Dependabot groups minor updates by ecosystem but does not auto-merge them. Review changelogs and run the full workflow before merging. Keep production and development npm updates in separate groups.

### Low: patch updates

Patch updates may auto-merge through `dependabot-automerge.yml` only when Dependabot identifies a semver patch update and repository branch protection requires the dependency audit workflow to pass. Security updates remain subject to the scanner result and review policy.

## Breaking-change analysis checklist

For every major PR:

- inspect `CHANGELOG`, `MIGRATION`, `UPGRADING`, release notes, and codemods;
- compare TypeScript exports or Python/Rust public APIs where applicable;
- search imports and call sites before changing the dependency;
- identify tests and critical flows that exercise the dependency;
- update lockfiles with the project-supported runtime;
- record removed APIs, replacements, migration steps, and rollback version in the PR body.

## Recommended batches

1. Security-only fixes, one ecosystem at a time.
2. Python lockfile and scanner baseline.
3. npm minor and patch updates, grouped by production versus development.
4. Cargo minor and patch updates.
5. One major dependency at a time, never mixed with feature work.
6. GitHub Actions updates separately from runtime dependencies.

## Rollback

1. Stop auto-merge and mark the dependency PR blocked.
2. Revert the merge commit, or restore the previous manifest and lockfile from the last known-good commit.
3. Run `npm ci`, reinstall the pinned Python constraints, or run `cargo check --locked`.
4. Re-run the dependency audit workflow and the application build.
5. Pin the problematic dependency through the ecosystem's supported constraint mechanism and document the reason and review date.

Never restore credentials, databases, caches, generated binaries, or raw provider URLs as part of a dependency rollback.
