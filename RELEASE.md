# Release 0.177.87

- Date: 2026-03-29

## Summary
- implemented ADR 0260 by deploying repo-managed Nextcloud on docker-runtime-lv3 with a dedicated postgres backend, shared-edge DAV publication, and verified personal-data-plane replay on the latest realistic origin/main baseline

## Platform Impact
- platform version advanced to 0.130.59 after the exact-main ADR 0260 replay re-verified the Nextcloud personal data plane, dedicated PostgreSQL backend, and shared-edge DAV publication on top of the 0.130.58 baseline

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
