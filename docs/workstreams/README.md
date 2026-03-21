# Workstreams

This directory exists to make parallel implementation safe.

## Model

- one ADR can have one or more implementation workstreams
- one chat thread should usually work on one workstream
- one active workstream should usually have one dedicated branch and one dedicated git worktree
- `workstreams.yaml` is the machine-readable registry
- the files in this directory are the human-readable handoff documents
- protected release files are reconciled later on `main`, not continuously on every branch

## Branch Boundaries

Workstream branches are expected to update:

- implementation code for their own scope
- their own ADR changes if needed
- their own runbook material
- their own workstream file
- their own `workstreams.yaml` entry

Workstream branches should avoid updating:

- `VERSION`
- numbered release sections in `changelog.md`
- canonical observed-state sections in `versions/stack.yaml`
- top-level integrated summaries in `README.md`

Those are integration surfaces and should normally be updated only when work is merged to `main`.

## Required Fields Per Workstream

Each workstream document should record:

- ADR reference
- branch name
- worktree path
- status
- dependencies
- conflicting workstreams
- shared surfaces
- intended files to touch
- live surfaces to touch
- verification commands
- merge criteria

## Status Meanings

- `ready`: queued and available to pick up
- `in_progress`: actively being implemented in a branch
- `blocked`: cannot continue until a dependency or external input is resolved
- `ready_for_merge`: implementation is complete and waiting for integration
- `merged`: merged to `main`
- `live_applied`: merged and applied to the real platform

## Template

Use [TEMPLATE.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/TEMPLATE.md) for new workstreams.
