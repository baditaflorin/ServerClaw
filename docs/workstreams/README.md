# Workstreams

This directory exists to make parallel implementation safe.

## Model

- one ADR can have one or more implementation workstreams
- one chat thread should usually work on one workstream
- one active workstream should usually have one dedicated branch and one dedicated git worktree
- `workstreams.yaml` is the machine-readable registry
- the files in this directory are the human-readable handoff documents

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
