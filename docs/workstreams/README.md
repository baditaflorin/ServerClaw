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
- validation surfaces when their work changes the minimum merge gate

Workstream branches should avoid updating:

- `VERSION`
- `changelog.md` and `docs/release-notes/`
- canonical observed-state sections in `versions/stack.yaml`
- top-level integrated summaries in `README.md`

Those are integration surfaces and should normally be updated only when work is merged to `main`.

## Canonical Truth Metadata

When a workstream should feed the integration-only canonical outputs, add a `canonical_truth` block to its `workstreams.yaml` entry.

- `changelog_entry` supplies one assembled `## Unreleased` bullet
- `release_bump` declares the minimum repo version bump for that workstream
- `included_in_repo_version` stays `null` until the release manager cuts the version that includes the workstream
- `latest_receipts` maps capability IDs to the live-apply receipt that should appear in `versions/stack.yaml`

## Minimum Merge Gate

Before a workstream is merged to `main`, the minimum repository validation command is:

```bash
make validate
```

If a workstream intentionally adds a new validation stage, update the validation script, CI workflow, and the validation runbook in the same change.

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

## Starting A Workstream

Preferred entry point:

```bash
make start-workstream WORKSTREAM=adr-0011-monitoring
```

This uses [scripts/create-workstream.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/create-workstream.sh) to:

- read the branch and worktree path from [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
- create the worktree if it does not exist
- attach it to the correct `codex/` branch

## Template

Use [TEMPLATE.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/TEMPLATE.md) for new workstreams.
