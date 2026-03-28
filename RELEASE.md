# Release 0.177.47

- Date: 2026-03-28

## Summary
- integrated ADR 0197 on current main by replaying the public Dify edge, re-verifying the governed `api.lv3.org` tool bridge, and preserving packaged API gateway runbook compatibility plus worktree-safe smoke tracing

## Platform Impact
- bumped the live platform version to 0.130.42 after replaying `make converge-dify` and `make converge-api-gateway` from the merged-main candidate so `agents.lv3.org` is publicly healthy, governed Dify tool calls succeed again through `api.lv3.org`, and linked-worktree smoke verification now discovers shared Langfuse secrets automatically

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
