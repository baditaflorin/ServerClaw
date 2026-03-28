# Workstream WS-0226: Host Control Loops Live Apply

- ADR: [ADR 0226](../adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md)
- Title: Live apply the systemd service, timer, and path baseline for host-resident control loops on `proxmox_florin`
- Status: in_progress
- Implemented In Repo Version: pending merge to main
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
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

- in progress

## Notes For The Next Assistant

- protected integration files stay untouched on this branch unless this thread
  explicitly becomes the final mainline integration step
- live verification must prove both the timer and the path unit, not only the
  oneshot service
