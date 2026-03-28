# Workstream WS-0226: Host Control Loops Live Apply

- ADR: [ADR 0226](../adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md)
- Title: Live apply the systemd service, timer, and path baseline for host-resident control loops on `proxmox_florin`
- Status: live_applied
- Implemented In Repo Version: 0.177.50
- Live Applied In Platform Version: 0.130.38
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0226-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0226-live-apply`
- Owner: codex
- Depends On: `adr-0204-self-correcting-automation-loops`, `adr-0220-bootstrap-and-recovery-sequencing-for-environment-cells`, `adr-0224-server-resident-operations-as-the-default-control-model`
- Conflicts With: none
- Shared Surfaces: `Makefile`, `config/workflow-catalog.json`, `config/command-catalog.json`, `playbooks/proxmox-install.yml`, `collections/ansible_collections/lv3/platform/roles/proxmox_host_control_loops/`, `docs/runbooks/configure-host-control-loops.md`, `docs/adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md`, `docs/adr/.index.yaml`, `tests/test_proxmox_host_control_loops_role.py`, `docs/workstreams/ws-0226-live-apply.md`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- add a reusable Proxmox-host role that installs the canonical ADR 0226
  `systemd` service, timer, and path units for host-resident control loops
- wire the new role into the existing Proxmox host automation and register a
  dedicated make target plus workflow entrypoint
- document the host-side operator procedure and record live-apply evidence
- verify the path-trigger, timer activation, status-file write, and journal
  visibility end to end from this isolated worktree

## Expected Repo Surfaces

- `Makefile`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `playbooks/proxmox-install.yml`
- `collections/ansible_collections/lv3/platform/roles/proxmox_host_control_loops/`
- `docs/runbooks/configure-host-control-loops.md`
- `docs/adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md`
- `docs/adr/.index.yaml`
- `tests/test_proxmox_host_control_loops_role.py`
- `docs/workstreams/ws-0226-live-apply.md`
- `workstreams.yaml`
- `receipts/live-applies/2026-03-28-adr-0226-host-control-loops-live-apply.json`

## Expected Live Surfaces

- `proxmox_florin` host-only `systemd` units:
  `lv3-host-control-loop-reconcile.service`,
  `lv3-host-control-loop-reconcile.timer`, and
  `lv3-host-control-loop-reconcile.path`
- host-local status and run history under `/var/lib/lv3-host-control-loops/`

## Verification

- `make workflow-info WORKFLOW=configure-host-control-loops`, `uv run --with pytest pytest -q tests/test_proxmox_host_control_loops_role.py`, and `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json role-argument-specs ansible-syntax data-models` all passed from rebased branch head `b56e6dee15d4caca0e326235bdc7403a4b426e49`.
- `make configure-host-control-loops` replayed cleanly from `b56e6dee15d4caca0e326235bdc7403a4b426e49` with `proxmox_florin ok=33 changed=2 failed=0`; the replay updated the service unit and cleared a stale failed state before reasserting the timer and path units.
- `sudo systemctl show` on `proxmox_florin` reported `lv3-host-control-loop-reconcile.service Result=success ActiveState=inactive`, the timer as `active/waiting` with `NextElapseUSecRealtime=Sat 2026-03-28 18:00:59 CET` and `LastTriggerUSec=Sat 2026-03-28 17:31:04 CET`, and the path unit as `active/waiting` with `Triggers=lv3-host-control-loop-reconcile.service`.
- `sudo systemctl start lv3-host-control-loop-reconcile.service` recorded `trigger: scheduled_or_manual` at `2026-03-28T16:39:33Z` with history file `/var/lib/lv3-host-control-loops/runs/20260328T163933Z.json`.
- Writing `ws-0226-path-20260328T163913Z` to `/var/lib/lv3-host-control-loops/requests/reconcile.request` was consumed immediately; `latest.json` recorded `trigger: path_request` with the request payload at `2026-03-28T16:39:13Z`, journald showed a clean start and finish at `17:39:13 CET`, and `/var/lib/lv3-host-control-loops/runs/20260328T163913Z.json` was created.
- The integrated `0.177.50` candidate commit `c11de34d3495e7617488246cda6577b1af75b672` passed `make pre-push-gate`, including `alert-rule-validation`, `ansible-lint`, `ansible-syntax`, `artifact-secret-scan`, `dependency-direction`, `dependency-graph`, `integration-tests`, `packer-validate`, `policy-validation`, `schema-validation`, `security-scan`, `service-completeness`, `tofu-validate`, `type-check`, and `yaml-lint`.
- As part of the ADR 0224 exact-main proof, the integrated `0.177.50` candidate kept the live units healthy after the host-local `ansible-pull` replay from private Gitea snapshot `c3ef5f172c7ec178a692b0ee772d2d1349096ab5`: request payload `ws-0224-path-20260328T204845Z` was consumed into `/var/lib/lv3-host-control-loops/runs/20260328T204846Z.json`, and an immediate manual `systemctl start` recorded `trigger: scheduled_or_manual` at `2026-03-28T20:49:17Z` with history file `/var/lib/lv3-host-control-loops/runs/20260328T204917Z.json`.

## Outcome

- ADR 0226 is live on `proxmox_florin` with repo-managed `systemd` service, timer, and path units plus durable state under `/var/lib/lv3-host-control-loops/`.
- Live verification uncovered and fixed a unit-contract bug in the initial baseline: a `oneshot` service with `Restart=on-failure` plus `StartLimitIntervalSec=900` and `StartLimitBurst=3` can trip `start-limit-hit` after normal timer, path, and manual starts because systemd rate-limits successful starts too.
- The repaired branch now delegates retry to the timer, path trigger, or explicit operator start and clears any latched failed state during replay with `systemctl reset-failed`.

## Mainline Integration

- Release `0.177.50` now carries ADR 0226 into merged repository truth with refreshed protected surfaces, generated artifacts, and receipt mapping under `host_control_loops`.
- The exact-main ADR 0224 replay re-proved the already-live unit contract without another controller-side `make configure-host-control-loops` mutation because the live host already matched the repo-managed baseline.
