# Release 0.125.0

- Date: 2026-03-24

## Summary
- Implemented ADR 0128 with a repository-managed composite health index that turns uptime, SLO, drift, incident, maintenance, and mutation state into one shared per-service score.
- Added `platform/health`, the Windmill `refresh_composite` worker, and the `health.composite` migration so the index has a durable refresh and storage path.
- Switched the platform API, the new `lv3 health` command, and the goal compiler gate to the shared composite index.
- Added focused verification for simulated failures across the scorer, Windmill wrapper, API endpoint, CLI surface, and goal compiler.

## Platform Impact
- repository version advances to 0.125.0; no live platform version bump is recorded because the health schema and Windmill schedule still require apply from `main`

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
