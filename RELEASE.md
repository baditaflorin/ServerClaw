# Release 0.177.99

- Date: 2026-03-30

## Summary
- implements ADR 0283 by deploying Plausible Analytics on docker-runtime-lv3, publishing analytics.lv3.org through the shared edge, injecting the tracker into declared public pages, and recording synchronized branch-local live-apply proof before exact-main integration

## Platform Impact
- adds repo-managed Plausible Analytics automation, receipts, and tracker injection surfaces for ADR 0283; the exact-main replay will advance the platform version once verified

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
