# Release 0.177.39

- Date: 2026-03-28

## Summary
- integrated ADR 0211 by promoting the shared policy registry into main and re-verifying the governed headscale live-apply path from merged main

## Platform Impact
- keeps the platform at 0.130.38; this release integrates ADR 0211 on top of 0.177.38 so the shared policy registry now governs redundancy, capacity-class, and placement rules across validation, docs, and the verified headscale live-apply path already running on the platform

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
