# Release 0.177.87

- Date: 2026-03-29

## Summary
- records ADR 0251 exact-main durable verification on the latest realistic origin/main by marking the stage-scoped smoke suite and promotion-gate workflow fully live, preserving the live worker checkout, gate-status, runtime-assurance, and ops-portal verification on release 0.177.87 while the current verified platform baseline remains 0.130.59

## Platform Impact
- no additional platform-version bump; this release records ADR 0251 exact-main durable verification on the already-verified 0.130.59 platform baseline, promotes the canonical mainline receipt for stage-smoke and promotion-gate evidence, and marks ADR 0251 fully live on main

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
