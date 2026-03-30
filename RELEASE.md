# Release 0.177.101

- Date: 2026-03-30

## Summary
- replays ADR 0251 on the latest merged mainline by pinning the Windmill worker checkout to the active worktree during converge-windmill, replaying the Docker publication, step-ca, OpenBao, and stage-smoke verification paths on the live server, and refreshing the canonical smoke-suite and promotion-gate receipt

## Platform Impact
- records ADR 0251 exact-main live-apply verification on top of current mainline, preserves the pinned Windmill worker checkout sync during converge-windmill, refreshes the canonical smoke-suite and promotion-gate receipt, and advances the verified platform baseline after the newest exact-main replay

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
