# Preview Environments

This runbook documents the repo-managed path for creating, validating, and destroying ADR 0185 branch-scoped ephemeral preview environments.

## Purpose

Use a preview environment when a branch needs a realistic live Proxmox target without mutating production or the long-lived staging lane.

The current implementation builds previews from the current branch manifest plus the profile catalog in [config/preview-environment-profiles.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/config/preview-environment-profiles.json).

## Current Model

- base domain: `preview.lv3.org`
- current profile catalog: `runtime-smoke`
- TTL enforcement: ADR 0106 governed ephemeral VM tags plus the existing preview/fixture reaper path
- preview network boundary: shared `vmbr20` pool on `10.20.10.0/24`
- current preview IP pool: `10.20.10.130-10.20.10.199`
- current preview VMID pool: the governed ephemeral range `910-979`

Each preview records:

- owning branch and workstream
- TTL and destroy policy
- selected profile and declared service subset
- manifest snapshot metadata from the branch-local `build/platform-manifest.json`
- smoke and synthetic validation results
- durable evidence under `receipts/preview-environments/` after teardown

## Create

Refresh the branch manifest and create the preview:

```bash
make preview-create WORKSTREAM=ws-0185-live-apply PROFILE=runtime-smoke BRANCH=codex/ws-0185-live-apply JSON=true
```

Expected result:

- a preview domain like `ws-0185-live-apply.preview.lv3.org`
- one or more ephemeral VMs provisioned on `vmbr20`
- local active state under `.local/preview-environments/active/`
- member-level governed receipts under `receipts/fixtures/` while the preview is active

## Validate

Re-run smoke and synthetic validation before claiming the preview is good:

```bash
make preview-validate PREVIEW_ID=<preview-id> JSON=true
```

The current `runtime-smoke` profile validates:

- `ops` access on the preview VM
- Docker service readiness
- `docker info` from the guest

## Destroy And Record Evidence

Tear the preview down after verification:

```bash
make preview-destroy PREVIEW_ID=<preview-id> JSON=true
```

Expected result:

- all preview VMs are destroyed from Proxmox
- local state is archived under `.local/preview-environments/archive/`
- durable evidence is written to `receipts/preview-environments/<preview-id>.json`
- a live-apply receipt is written to `receipts/live-applies/preview/<preview-id>.json`

## Inspect

List active previews:

```bash
make preview-list
```

Show one preview:

```bash
make preview-info PREVIEW_ID=<preview-id> JSON=true
```

Use `ARCHIVED=true` with `preview-info` after teardown.

## Merge Notes

Preview evidence on a workstream branch documents that ADR 0185 is live-applied and end-to-end verified, but the protected integration files still wait for merge to `main`:

- `README.md`
- `VERSION`
- release sections in `changelog.md`
- `versions/stack.yaml`

Update those only during the final integrated mainline replay.
