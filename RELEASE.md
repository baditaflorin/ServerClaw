# Release 0.177.111

- Date: 2026-03-31

## Summary
- integrates ADR 0291 into main by replaying JupyterHub as the authenticated interactive notebook environment on the latest realistic origin/main baseline, preserving the verified notebooks.lv3.org, Keycloak, Ollama, platform-context, and smoke-user contract without inventing a new branch-local truth source

## Platform Impact
- platform version remains 0.130.73 because ADR 0291 first became true on 0.130.71; this release integrates the rebased JupyterHub exact-main proof, validation fixes, and concurrent-worktree automation hardening onto main without introducing a new platform-version bump.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
