# Release 0.177.61

- Date: 2026-03-29

## Summary
- implemented ADR 0241 by adding a Tiptap-backed bounded-knowledge editor to the repo-managed Windmill operator-access admin surface, regenerating the raw-app dependency lock, and hardening governed Windmill live replay from concurrent non-primary worktrees

## Platform Impact
- no live platform version bump; this release records the verified ADR 0241 Tiptap rich-notes rollout while the current mainline platform baseline remains 0.130.44

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
