# Release 0.177.78

- Date: 2026-03-29

## Summary
- records ADR 0265 exact-main evidence on the newest current mainline by replacing mutable remote validation mirrors with immutable repository snapshots, fresh per-run builder namespaces, and repo-shape-safe remote validation for the build gateway

## Platform Impact
- establishes platform version 0.130.53 because the 2026-03-29 newest exact-main replay verified `make check-build-server` and `make remote-validate` on `docker-build-lv3`, and the publish path re-runs the full pre-push gate on the exact commit delivered to `main`

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
