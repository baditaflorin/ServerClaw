# Workstream WS-0227: Bounded Command Execution Live Apply

- ADR: [ADR 0227](../adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md)
- Title: Live apply bounded governed command execution through `systemd-run` on the server-resident runtime
- Status: merged
- Implemented In Repo Version: 0.177.46
- Live Applied In Platform Version: 0.130.41
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0227-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0227-live-apply`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0170-platform-wide-timeout-hierarchy`, `adr-0224-server-resident-operations-as-the-default-control-model`, `adr-0226-systemd-units-timers-and-paths-for-host-resident-control-loops`
- Conflicts With: none
- Shared Surfaces: `config/command-catalog.json`, `config/agent-tool-registry.json`, `scripts/agent_tool_registry.py`, `scripts/command_catalog.py`, `scripts/governed_command.py`, `scripts/governed_command_runtime.py`, `scripts/controller_automation_toolkit.py`, `scripts/maintenance_window_tool.py`, `scripts/platform_observation_tool.py`, `scripts/fault_injection.py`, `platform/repo.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `docs/runbooks/command-catalog-and-approval-gates.md`, `docs/runbooks/bounded-command-execution.md`, `docs/adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md`, `docs/adr/.index.yaml`, `tests/test_agent_tool_registry.py`, `tests/test_controller_automation_toolkit.py`, `tests/test_governed_command.py`, `tests/test_governed_command_runtime.py`, `receipts/live-applies/2026-03-28-adr-0227-bounded-command-execution-live-apply.json`, `receipts/live-applies/2026-03-28-adr-0227-bounded-command-execution-mainline-live-apply.json`, `workstreams.yaml`

## Scope

- move governed command execution from inline controller-shell `subprocess.run(...)` calls into bounded transient units started with `systemd-run`
- keep the command catalog as the execution contract source by adding explicit runtime execution profiles and per-command timeout declarations
- stage controller-local file secrets into repo-local runtime paths so server-resident commands can keep using repo-managed Make targets and worker-local `.local/` surfaces
- live-apply the bounded execution path onto `docker-runtime-lv3`, verify it with a governed command end to end, and leave protected shared integration files for the main merge step

## Expected Repo Surfaces

- `config/command-catalog.json`
- `config/agent-tool-registry.json`
- `scripts/agent_tool_registry.py`
- `scripts/command_catalog.py`
- `scripts/governed_command.py`
- `scripts/governed_command_runtime.py`
- `scripts/controller_automation_toolkit.py`
- `scripts/maintenance_window_tool.py`
- `scripts/platform_observation_tool.py`
- `scripts/fault_injection.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `docs/runbooks/command-catalog-and-approval-gates.md`
- `docs/runbooks/bounded-command-execution.md`
- `docs/adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0227-live-apply.md`
- `workstreams.yaml`

## Expected Live Surfaces

- the `docker-runtime-lv3` repo checkout gains the compatibility symlink, writable governed-command log and receipt directories, and writable worker output directories required for `ops`-scoped execution
- approved governed commands run as transient `systemd-run` units owned by `ops`, not inline in the initiating controller shell
- live verification captures the transient unit name, receipt path, and stdout/stderr log paths from a real governed command replay

## Verification

- `python3 scripts/command_catalog.py --validate`
- `python3 scripts/agent_tool_registry.py --validate`
- `uv run --with pytest --with pyyaml pytest -q tests/test_maintenance_window_tool.py tests/test_governed_command.py tests/test_governed_command_runtime.py tests/test_controller_automation_toolkit.py tests/test_lv3_cli.py`
- `./scripts/validate_repo.sh agent-standards`
- `make converge-windmill`
- authenticated governed replay of `network-impairment-matrix` through `python3 scripts/governed_command.py`

## Live Apply Outcome

- branch-local live apply succeeded on 2026-03-28 from the isolated worktree, and governed `network-impairment-matrix` execution now runs as transient `systemd-run` units with durable stdout, stderr, and receipt capture under `.local/governed-command/`
- the successful end-to-end replay returned unit `lv3-governed-network-impairment-matrix-79b10a86f237`, receipt `/srv/proxmox_florin_server/.local/governed-command/receipts/lv3-governed-network-impairment-matrix-79b10a86f237.json`, and report `/srv/proxmox_florin_server/.local/network-impairment-matrix/latest.json` with `status: planned` and `entry_count: 4`
- the first replay exposed pre-existing root-owned execution-lane registry files on `docker-runtime-lv3`; the branch fixed the role contract to manage those files as mutable runtime surfaces, and the live guest required one one-time repair `sudo chmod 0666 /srv/proxmox_florin_server/.local/state/execution-lanes/registry.json /srv/proxmox_florin_server/.local/state/execution-lanes/registry.lock` before the final successful governed replay

## Mainline Integration Outcome

- merged to `main` in repository version `0.177.46`
- bumped the live platform version to `0.130.41` after replaying `make converge-windmill` from the rebased merged-main-equivalent candidate and re-verifying the governed `network-impairment-matrix` path
- the merged-main governed replay returned unit `lv3-governed-network-impairment-matrix-9dbb73e9a6e9`, receipt `/srv/proxmox_florin_server/.local/governed-command/receipts/lv3-governed-network-impairment-matrix-9dbb73e9a6e9.json`, and report `/srv/proxmox_florin_server/.local/network-impairment-matrix/latest.json` with `status: planned` and `entry_count: 4`
- the rebased mainline candidate also repaired the shared YAML fallback regression introduced by the `platform.repo` helper refactor so controller automation still treats `tag:platform-operator` and `https://...` list entries as scalars

## Live Evidence

- branch-local live-apply receipt: `receipts/live-applies/2026-03-28-adr-0227-bounded-command-execution-live-apply.json`
- merged-main-equivalent live-apply receipt: `receipts/live-applies/2026-03-28-adr-0227-bounded-command-execution-mainline-live-apply.json`
- successful runtime receipt on `docker-runtime-lv3`: `/srv/proxmox_florin_server/.local/governed-command/receipts/lv3-governed-network-impairment-matrix-79b10a86f237.json`
- successful runtime stdout log: `/srv/proxmox_florin_server/.local/governed-command/logs/lv3-governed-network-impairment-matrix-79b10a86f237.stdout.log`
- successful runtime stderr log: `/srv/proxmox_florin_server/.local/governed-command/logs/lv3-governed-network-impairment-matrix-79b10a86f237.stderr.log`

## Merge-To-Main Notes

- remaining for merge to `main`: none
