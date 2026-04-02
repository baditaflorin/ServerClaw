# Release 0.177.142

- Date: 2026-04-02

## Summary
- adds a repo-managed cmdk command palette to the Windmill operator access admin surface, backed by ADR 0121 search-fabric results and browser-local favorites/recents without bypassing governed mutations

## Platform Impact
- platform version advances to 0.130.90 after the exact-main ADR 0311 replay re-verifies the repo-managed cmdk command palette, ADR and runbook search helper, and governed Windmill operator-admin open flows on top of the 0.130.89 baseline while preserving the ADR 0316 journey analytics surfaces already live on main

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
