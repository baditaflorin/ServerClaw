# WS-0514 — Repository release 0.179.47

## Purpose

Cut a patch release for the merged Woodpecker-only public CI and service-
completeness scoping changes, then publish the resulting sanitized snapshot.

## Scope

- Advance repository version to `0.179.47`; leave `platform_version` unchanged.
- Generate release notes, manifest, README status, ADR index, and discovery
  artifacts from current `main`.
- Refresh ServerClaw through its reviewed publication PR.

## Verification

- `scripts/check_release_readiness.py --base-ref origin/main --enforce`
- Workstream registry, ADR index, discovery, release-note summaries, and README
  generated-artifact checks.
- Woodpecker push and PR checks for the source release PR and public snapshot PR.

This is single-commit release-metadata housekeeping; Plane sync is intentionally
skipped under the repository's explicit exception.
