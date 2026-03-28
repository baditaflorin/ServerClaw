# Release 0.177.34

- Date: 2026-03-28

## Summary
- implemented ADR 0212 by governing critical integrated product ADRs with machine-checked replaceability scorecards, vendor exit plans, and live docs publication evidence
- aligned the dependency-graph and generated-diagram validation paths so the docs-site and pre-push gate now agree on the governed generated artifacts

## Platform Impact
- no platform version bump; the docs-governance rollout was already live-verified on platform version `0.130.36`, and this release records that verified state on `main` without introducing a second live apply.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
