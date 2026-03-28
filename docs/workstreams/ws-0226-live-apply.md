# Workstream WS-0226: Host Control Loops Live Apply

- ADR: [ADR 0226](../adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md)
- Title: Live apply the systemd service, timer, and path baseline for host-resident control loops on `proxmox_florin`
- Status: live_applied
- Implemented In Repo Version: pending merge to main
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
- `make pre-push-gate` was exercised and failed only on shared integration surfaces outside ADR 0226 ownership: stale generated artifacts in `docs/diagrams` and `build/platform-manifest.json`, plus a timeout in the containerized `ansible-lint` step on the local arm64 host.

## Outcome

- ADR 0226 is live on `proxmox_florin` with repo-managed `systemd` service, timer, and path units plus durable state under `/var/lib/lv3-host-control-loops/`.
- Live verification uncovered and fixed a unit-contract bug in the initial baseline: a `oneshot` service with `Restart=on-failure` plus `StartLimitIntervalSec=900` and `StartLimitBurst=3` can trip `start-limit-hit` after normal timer, path, and manual starts because systemd rate-limits successful starts too.
- The repaired branch now delegates retry to the timer, path trigger, or explicit operator start and clears any latched failed state during replay with `systemctl reset-failed`.

## Mainline Integration

- Protected integration files intentionally remain untouched on this workstream branch.
- Merge-to-main still needs the final repo version assignment plus the corresponding `VERSION`, `changelog.md`, top-level `README.md`, and `versions/stack.yaml` updates.
- The current pre-push gate also requires a separate shared-surface integration step to refresh `build/platform-manifest.json` and regenerate `docs/diagrams` before a mainline push can go green end to end.

## Notes For The Next Assistant

- protected integration files stay untouched on this branch unless this thread
  explicitly becomes the final mainline integration step
- rerun `make pre-push-gate` only after the shared generated artifacts outside
  ADR 0226 ownership have been refreshed on the integration branch
