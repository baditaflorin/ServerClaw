# Workstream ws-0226-main-merge

- ADR: [ADR 0226](../adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md)
- Title: Finalize ADR 0226 exact-main evidence on `origin/main`
- Status: merged
- Included In Repo Version: 0.177.55
- Platform Version Observed During Merge: 0.130.43
- Release Date: 2026-03-28
- Branch: `codex/ws-0226-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0226-main-merge`
- Owner: codex
- Depends On: `ws-0226-live-apply`

## Purpose

Carry the remaining ADR 0226 exact-main evidence onto the current
`origin/main`, preserve the earlier merged-main replay receipt and repaired
host-control-loop contract, recut the protected release-truth surfaces on top
of repository version `0.177.54`, and push the fully validated `0.177.55`
result to `origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0226-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.55.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md`
- `docs/runbooks/configure-host-control-loops.md`
- `docs/workstreams/ws-0226-live-apply.md`
- `Makefile`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/ansible-role-idempotency.yml`
- `playbooks/proxmox-install.yml`
- `collections/ansible_collections/lv3/platform/roles/proxmox_host_control_loops/`
- `tests/test_proxmox_host_control_loops_role.py`
- `receipts/live-applies/2026-03-28-adr-0226-host-control-loops-live-apply.json`
- `receipts/live-applies/2026-03-28-adr-0226-host-control-loops-mainline-live-apply.json`

## Plan

- rebase the preserved ADR 0226 exact-main follow-up onto the newer
  `0.177.54` `origin/main` baseline without reintroducing stale shared-surface
  edits
- cut follow-on release `0.177.55` with no platform-version bump because the
  latest-main ADR 0226 replay was already verified on platform `0.130.42`
- refresh generated release, status, portal, and manifest surfaces from the
  final exact-main registry state before validating and pushing `main`

## Verification

- `git checkout origin/main -- workstreams.yaml` restored the current mainline registry before reapplying only the ADR 0226 live-apply plus main-merge entries, avoiding the stale-registry regression that would have dropped newer workstreams from `origin/main`
- `make workflow-info WORKFLOW=configure-host-control-loops` and `uv run --with pytest pytest -q tests/test_proxmox_host_control_loops_role.py` both passed on the merged-main candidate
- `make configure-host-control-loops` completed successfully from this worktree with `proxmox_florin ok=33 changed=0 failed=0`
- host checks after the merged-main replay reported `lv3-host-control-loop-reconcile.service Result=success ActiveState=inactive SubState=dead UnitFileState=static`, the timer as `active/waiting` with `NextElapseUSecRealtime=Sat 2026-03-28 22:30:59 CET` and `LastTriggerUSec=Sat 2026-03-28 22:01:21 CET`, and the path unit as `active/waiting` with `Triggers=lv3-host-control-loop-reconcile.service`
- a fresh manual start recorded `trigger: scheduled_or_manual` at `2026-03-28T21:24:49Z` with history file `/var/lib/lv3-host-control-loops/runs/20260328T212449Z.json`
- a fresh path-triggered request `{"reason":"ws-0226-main-merge-20260328T2125Z"}` was consumed immediately, recorded `trigger: path_request` at `2026-03-28T21:25:04Z`, and produced history file `/var/lib/lv3-host-control-loops/runs/20260328T212504Z.json`
- rebasing commit `ca501fa8` onto newer `origin/main` commit `2fb27abe` kept the ADR 0226 source-of-truth follow-up isolated to seven intended files while inheriting the newer `0.177.54` ADR 0233 release surfaces from `main`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records ADR 0226 exact-main evidence already verified on platform 0.130.42 while the current live baseline remains 0.130.43" --dry-run` reported `Current version: 0.177.54`, `Next version: 0.177.55`, and `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records ADR 0226 exact-main evidence already verified on platform 0.130.42 while the current live baseline remains 0.130.43"` prepared release `0.177.55`

## Outcome

- release `0.177.55` records ADR 0226 exact-main evidence on top of the current `0.177.54` baseline without a platform-version bump; the first repository release that carried ADR 0226 itself remains `0.177.52`
- the merged-main-equivalent replay receipt is `receipts/live-applies/2026-03-28-adr-0226-host-control-loops-mainline-live-apply.json`
- the current `main` platform baseline remains `0.130.43`, while ADR 0226 itself first became true on `0.130.38`
