# Release Process

## Purpose

This repository now supports parallel ADR implementation. That requires a clear distinction between branch work, merged repo truth, and live platform truth.

## Rules

1. Branch and workstream phase
   - create or claim a workstream in `workstreams.yaml`
   - use one branch per workstream, with the `codex/` prefix
   - prefer one git worktree per active workstream
   - use `make start-workstream WORKSTREAM=<id>` to create the correct worktree
   - update the workstream document while implementation is in progress
   - do not bump `VERSION` just because a branch changes
   - do not update `versions/stack.yaml` with speculative branch-only platform state
   - do not rewrite shared release files from a workstream branch
2. Merge phase
   - merge the completed workstream to `main`
   - bump `VERSION` once on `main`
   - move relevant changelog notes from `Unreleased` into a versioned section
   - update `workstreams.yaml` status to reflect merge completion
3. Live apply phase
   - apply merged automation from `main`
   - verify the real platform state
   - bump `platform_version` in `versions/stack.yaml`
   - update observed state in `versions/stack.yaml`
   - mark the workstream as `live_applied: true`

## Protected Integration Files

These files are owned by the integration step on `main`, not by normal workstream branches:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION`
- release sections in `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md`
- canonical observed-state and release-track sections in `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml`
- top-level integrated status summaries in `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md`

Workstream branches should usually change:

- their own automation and tests
- their own ADR and runbook material
- their own file in `docs/workstreams/`
- their own entry in `workstreams.yaml`

## Integration Gate

Before merging a workstream to `main`, confirm:

- `make validate` passes
- if the workflow depends on controller-local secrets or external tokens, `make preflight WORKFLOW=<id>` passes for the relevant entry point
- the workstream document is current
- the touched ADR and runbook changes are committed
- shared-surface conflicts are resolved
- it is clear whether the change is repo-only or also live-applied

## Integration Ownership

- one human or one assistant thread should own the actual merge to `main`
- if several workstreams are moving quickly, use a temporary `codex/integration` branch to combine and test before merging to `main`
- do not let multiple workstream threads independently rewrite protected integration files

## Changelog Policy

- `Unreleased` is the scratch area on `main` for merged-but-not-version-cut notes
- cut a numbered section when `VERSION` changes on `main`
- do not create fake release entries on long-lived feature branches

## Recommended Worktree Commands

```bash
make start-workstream WORKSTREAM=adr-0011-monitoring
make start-workstream WORKSTREAM=adr-0014-tailscale
```

Equivalent raw git commands:

```bash
git worktree add ../proxmox_florin_server-monitoring -b codex/adr-0011-monitoring
git worktree add ../proxmox_florin_server-tailscale -b codex/adr-0014-tailscale
```
