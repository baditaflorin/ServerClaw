# Workstream ADR 0185: Branch-Scoped Ephemeral Preview Environments

- ADR: [ADR 0185](../adr/0185-branch-scoped-ephemeral-preview-environments.md)
- Title: Add a repo-managed branch preview lifecycle on the governed ephemeral VM pool and record branch-local evidence for create, validate, and destroy
- Status: live_applied
- Branch: `codex/ws-0185-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply`
- Owner: codex
- Depends On: `adr-0088-ephemeral-fixtures`, `adr-0106-ephemeral-environment-lifecycle-policy`, `adr-0156-agent-session-workspace-isolation`, `adr-0183-multi-environment-live-lanes`
- Conflicts With: none
- Shared Surfaces: `scripts/preview_environment.py`, `config/preview-environment-profiles.json`, `docs/schema/preview-environment-profiles.schema.json`, `docs/runbooks/preview-environments.md`, `receipts/live-applies/preview/`, `receipts/preview-environments/`, `workstreams.yaml`
- Ownership Manifest: `workstreams.yaml` `ownership_manifest`

## Scope

- add a preview profile catalog and schema for branch-scoped preview stacks
- implement create, validate, destroy, list, and show automation for previews on the existing governed ephemeral VM pool
- wire the preview catalog into repository validation and make entrypoints
- record one full create/validate/destroy cycle as branch-local live-apply evidence

## Non-Goals

- permanent shared staging replacements
- per-service preview publication on the shared public edge
- updating protected integration files before merge to `main`

## Expected Repo Surfaces

- [config/preview-environment-profiles.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/config/preview-environment-profiles.json)
- [docs/schema/preview-environment-profiles.schema.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/docs/schema/preview-environment-profiles.schema.json)
- [scripts/preview_environment.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/scripts/preview_environment.py)
- [docs/runbooks/preview-environments.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/docs/runbooks/preview-environments.md)
- [receipts/preview-environments](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/receipts/preview-environments)
- [receipts/live-applies/preview](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/receipts/live-applies/preview)

## Expected Live Surfaces

- one active preview environment can be created for this workstream on the governed ephemeral Proxmox pool
- the preview VM receives reaper-compatible TTL tags and can be validated over the normal Proxmox jump path
- the preview can be destroyed cleanly with durable evidence written back into the branch

## Ownership Notes

- this workstream owns the preview-environment catalog, lifecycle script, runbook, and preview evidence files
- shared contracts remain in `workstreams.yaml`, `Makefile`, `scripts/validate_repository_data_models.py`, and `scripts/live_apply_receipts.py`
- protected integration files stay untouched on this branch even after live apply succeeds

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_preview_environment.py tests/test_environment_catalog.py tests/test_live_apply_receipts.py -q`
- `python3 scripts/preview_environment.py validate-catalog`
- `make preview-list`
- `make generate-platform-manifest`
- `make validate-data-models`

## Live Apply Outcome

- committed-head replay preview id: `2026-03-27-adr-0185-ws-0185-live-apply-20260327t191234z`
- profile: `runtime-smoke`
- preview domain: `ws-0185-live-apply.preview.lv3.org`
- preview member: VM `910` at `10.20.10.130`
- lifecycle result: create, validate, and destroy all passed through repo automation
- smoke verification: `id ops >/dev/null`
- synthetic verification: `systemctl is-active docker`, `docker info >/dev/null`
- durable evidence:
  - [receipts/preview-environments/2026-03-27-adr-0185-ws-0185-live-apply-20260327t191234z.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/receipts/preview-environments/2026-03-27-adr-0185-ws-0185-live-apply-20260327t191234z.json)
  - [receipts/live-applies/preview/2026-03-27-adr-0185-ws-0185-live-apply-20260327t191234z.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0185-live-apply/receipts/live-applies/preview/2026-03-27-adr-0185-ws-0185-live-apply-20260327t191234z.json)

## Operational Notes

- early retries exposed a live host drift bug: `vmbr20` existed, but the nftables forward and postrouting chains were missing `10.20.10.0/24`
- branch-local replay of `playbooks/proxmox-staging-bridge.yml` restored the required host rules and unblocked preview guest egress
- preview converge now waits for SSH, waits for cloud-init and apt lock release, forces APT over IPv4, and provisions the guest via Proxmox host automation over the `ops@100.64.0.1` jump path
- the `runtime-smoke` preview member disables `docker_runtime_container_forward_compat_enabled` because the minimal preview image does not own a managed guest firewall contract
- during failed bring-up attempts, bounded manual cleanup of stale VM `910` with `qm stop` and `qm destroy --purge` was required; the final committed-head replay completed entirely through repo automation

## Merge Criteria

- preview lifecycle automation passes local validation
- one branch-scoped preview is created, validated, and destroyed on the live Proxmox estate
- ADR metadata and workstream state clearly record what was live-applied and what still waits for mainline integration

## Notes For The Next Assistant

- merge to `main` must still update the protected integration files that this workstream intentionally left unchanged:
  - `README.md`
  - `VERSION`
  - release sections in `changelog.md`
  - `versions/stack.yaml`
- keep the successful branch-local evidence above; do not reintroduce superseded preview receipts from earlier failed retries
