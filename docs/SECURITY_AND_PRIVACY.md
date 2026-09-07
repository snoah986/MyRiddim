# Security, Privacy, and Dependency Management

## Dependency security policy

- Keep `package-lock.json` and `src-tauri/Cargo.lock` under version control.
- Treat unpinned Python requirements as a reproducibility gap; CI must run `pip-audit` until a Python lock strategy is added.
- Dependabot opens weekly updates for npm, Python, Cargo, and GitHub Actions.
- The dependency audit workflow runs npm audit, pip-audit, cargo-audit, Python compilation, Rust compilation, and the frontend build on relevant changes.
- Only semver patch Dependabot updates are eligible for auto-merge, and branch protection must require the audit workflow.
- Major and minor updates require human review and a migration note.

## Vulnerability response

1. Record the package, affected version, advisory URL, CVE/GHSA, CVSS score, exploit status, and whether the package is direct or transitive.
2. Confirm exposure in this application and identify the affected route, desktop surface, or build artifact.
3. Prioritize:
   - Critical or High CVSS, exploited issues, and zero-days: immediate response.
   - Medium CVSS or security-relevant deprecations: remediate within 48 hours.
   - Low severity and non-production dev tooling: schedule with the next compatible batch.
4. Prefer the smallest compatible patch. If a major upgrade is required, isolate it in a dedicated branch and document the migration.
5. Run the full dependency workflow, `npm run build`, Python compilation, and `cargo check --locked` where applicable.
6. Record the resolution, accepted risk, or temporary pin with an owner and review date.

The current local audit reported zero high-or-higher npm vulnerabilities. Python and Rust results are intentionally pending CI scanner execution because those scanners were not installed locally during the audit.

## Privacy boundaries

This project handles YouTube session credentials, listening history, media cache, LAN invites, and optional remote controls. Dependency updates must not:

- add telemetry or remote logging without an explicit product decision;
- send `browser.json`, `oauth.json`, stats databases, invite tokens, or raw provider URLs to third-party services;
- expand the default backend bind beyond localhost;
- introduce packages that upload source, credentials, or usage data during install or runtime.

Review install scripts, new network clients, permissions, and Tauri capabilities in every dependency PR.

## CVE tracking record

Use this record format in the dependency PR or issue:

```text
Package:
Ecosystem:
Current resolved version:
Affected range:
CVE/GHSA:
CVSS / exploit status:
Direct or transitive:
Application impact:
Fixed version:
Validation:
Rollback version:
Owner / review date:
```

## Reporting

Do not publish credentials, raw YouTube headers, stream URLs, LAN invite tokens, or private stats in issues, logs, screenshots, or dependency reports. Report suspected supply-chain compromise privately to the repository owner with sanitized reproduction details.
