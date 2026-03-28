# Workstream ws-0226-main-merge

- ADR: [ADR 0226](../adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md)
- Title: Integrate ADR 0226 host control loops into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.52
- Platform Version Observed During Merge: 0.130.42
- Release Date: 2026-03-28
- Branch: `codex/ws-0226-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0226-main-merge`
- Owner: codex
- Depends On: `ws-0226-live-apply`

## Purpose

Carry the verified ADR 0226 live-apply branch onto the latest `origin/main`,
refresh the protected release and canonical-truth surfaces from the current
mainline baseline, replay `make configure-host-control-loops` from the merged
candidate, and push the fully validated result to `origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0226-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.52.md`
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

- restore `workstreams.yaml` to the latest `origin/main` baseline and reapply
  only the ADR 0226 live-apply plus main-merge registrations
- replay the ADR 0226 host control-loop converge from this merged-main
  candidate and record a canonical mainline receipt
- cut the next patch release on top of `0.177.51`, refresh generated release
  surfaces, rerun the validation bundle, and push the fast-forward result to
  `origin/main`

## Verification

- `git checkout origin/main -- workstreams.yaml` restored the current mainline registry before reapplying only the ADR 0226 live-apply plus main-merge entries, avoiding the stale-registry regression that would have dropped newer workstreams from `origin/main`
- `make workflow-info WORKFLOW=configure-host-control-loops` and `uv run --with pytest pytest -q tests/test_proxmox_host_control_loops_role.py` both passed on the merged-main candidate
- `make configure-host-control-loops` completed successfully from this worktree with `proxmox_florin ok=33 changed=0 failed=0`
- host checks after the merged-main replay reported `lv3-host-control-loop-reconcile.service Result=success ActiveState=inactive SubState=dead UnitFileState=static`, the timer as `active/waiting` with `NextElapseUSecRealtime=Sat 2026-03-28 22:30:59 CET` and `LastTriggerUSec=Sat 2026-03-28 22:01:21 CET`, and the path unit as `active/waiting` with `Triggers=lv3-host-control-loop-reconcile.service`
- a fresh manual start recorded `trigger: scheduled_or_manual` at `2026-03-28T21:24:49Z` with history file `/var/lib/lv3-host-control-loops/runs/20260328T212449Z.json`
- a fresh path-triggered request `{"reason":"ws-0226-main-merge-20260328T2125Z"}` was consumed immediately, recorded `trigger: path_request` at `2026-03-28T21:25:04Z`, and produced history file `/var/lib/lv3-host-control-loops/runs/20260328T212504Z.json`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "bumped the live platform version to 0.130.42 after replaying make configure-host-control-loops from the latest origin/main ADR 0226 merge candidate and re-verifying both manual and path-triggered host control-loop runs on proxmox_florin" --dry-run` reported `Current version: 0.177.51`, `Next version: 0.177.52`, and `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "bumped the live platform version to 0.130.42 after replaying make configure-host-control-loops from the latest origin/main ADR 0226 merge candidate and re-verifying both manual and path-triggered host control-loop runs on proxmox_florin"` prepared release `0.177.52`
- `make validate` passed on the final latest-main candidate, and `make pre-push-gate` passed end to end through the remote build-server validation path with green checks for `alert-rule-validation`, `ansible-lint`, `ansible-syntax`, `artifact-secret-scan`, `dependency-direction`, `dependency-graph`, `integration-tests`, `packer-validate`, `policy-validation`, `schema-validation`, `security-scan`, `service-completeness`, `tofu-validate`, `type-check`, and `yaml-lint`

## Outcome

- release `0.177.52` integrates ADR 0226 into `main` and records the protected integration surfaces on top of the current `0.177.51` baseline
- the merged-main-equivalent replay receipt is `receipts/live-applies/2026-03-28-adr-0226-host-control-loops-mainline-live-apply.json`
- the current `main` platform baseline advances to `0.130.42`, while ADR 0226 itself first became true on `0.130.38`
