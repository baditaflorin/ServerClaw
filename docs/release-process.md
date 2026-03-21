# Release Process

## Purpose

This repository now supports parallel ADR implementation. That requires a clear distinction between branch work, merged repo truth, and live platform truth.

## Rules

1. Branch and workstream phase
   - create or claim a workstream in `workstreams.yaml`
   - use one branch per workstream, with the `codex/` prefix
   - prefer one git worktree per active workstream
   - update the workstream document while implementation is in progress
   - do not bump `VERSION` just because a branch changes
   - do not update `versions/stack.yaml` with speculative branch-only platform state
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

## Integration Gate

Before merging a workstream to `main`, confirm:

- syntax and validation pass
- the workstream document is current
- the touched ADR and runbook changes are committed
- shared-surface conflicts are resolved
- it is clear whether the change is repo-only or also live-applied

## Changelog Policy

- `Unreleased` is the scratch area on `main` for merged-but-not-version-cut notes
- cut a numbered section when `VERSION` changes on `main`
- do not create fake release entries on long-lived feature branches

## Recommended Worktree Commands

```bash
git worktree add ../proxmox_florin_server-monitoring -b codex/adr-0011-monitoring
git worktree add ../proxmox_florin_server-tailscale -b codex/adr-0014-tailscale
```
