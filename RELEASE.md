# Release 0.177.86

- Date: 2026-03-29

## Summary
- implemented ADR 0251 by declaring stage-scoped smoke suites, enforcing structured smoke evidence on staged promotion receipts, seeding Windmill with the same repo-managed smoke runner used for live verification, and carrying the latest worker-runtime hardening needed for the exact-main replay path

## Platform Impact
- no live platform version bump yet; this release carries ADR 0251 onto `main` while the canonical platform baseline remains 0.130.58 until the exact-main Windmill replay records the new stage-smoke and promotion receipts

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
