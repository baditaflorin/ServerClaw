# Workstream WS-0227: Bounded Command Execution Live Apply

- ADR: [ADR 0227](../adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md)
- Title: Live apply bounded governed command execution through `systemd-run` on the server-resident runtime
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0227-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0227-live-apply`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0170-platform-wide-timeout-hierarchy`, `adr-0224-server-resident-operations-as-the-default-control-model`, `adr-0226-systemd-units-timers-and-paths-for-host-resident-control-loops`
- Conflicts With: none
- Shared Surfaces: `config/command-catalog.json`, `config/agent-tool-registry.json`, `scripts/agent_tool_registry.py`, `scripts/command_catalog.py`, `scripts/governed_command.py`, `scripts/governed_command_runtime.py`, `scripts/controller_automation_toolkit.py`, `scripts/maintenance_window_tool.py`, `scripts/platform_observation_tool.py`, `scripts/fault_injection.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `docs/runbooks/command-catalog-and-approval-gates.md`, `docs/runbooks/bounded-command-execution.md`, `docs/adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md`, `docs/adr/.index.yaml`, `tests/test_agent_tool_registry.py`, `tests/test_controller_automation_toolkit.py`, `tests/test_governed_command.py`, `tests/test_governed_command_runtime.py`, `receipts/live-applies/2026-03-28-adr-0227-bounded-command-execution-live-apply.json`, `workstreams.yaml`

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

- pending live apply

## Merge-To-Main Notes

- this branch must not bump `VERSION`, update numbered `changelog.md` release sections, or rewrite the top-level `README.md` summary
- if the live apply succeeds before merge, update this workstream doc, ADR 0227 metadata, and the live receipt in-branch so the final merge can safely carry the mainline release metadata later
