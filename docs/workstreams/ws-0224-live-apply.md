# Workstream WS-0224: Server-Resident Operations Default-Control Live Apply

- ADR: [ADR 0224](../adr/0224-server-resident-operations-as-the-default-control-model.md)
- Title: Verify and integrate the default server-resident control model from the latest `origin/main`
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0224-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0224-live-apply-r2`
- Owner: codex
- Depends On: `adr-0143-gitea`, `adr-0204-self-correcting-automation-loops`, `adr-0225-server-resident-reconciliation-via-ansible-pull`, `adr-0226-systemd-units-timers-and-paths-for-host-resident-control-loops`, `adr-0227-bounded-command-execution-via-systemd-run-and-approved-wrappers`, `adr-0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation`, `adr-0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0224-live-apply.md`, `docs/workstreams/ws-0226-live-apply.md`, `docs/adr/0224-server-resident-operations-as-the-default-control-model.md`, `docs/adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md`, `docs/adr/.index.yaml`, `docs/runbooks/server-resident-reconciliation.md`, `docs/runbooks/configure-host-control-loops.md`, `receipts/live-applies/`, `README.md`, `VERSION`, `changelog.md`, `RELEASE.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`

## Scope

- verify that the current production control model is server-resident by replaying the latest-main host-resident reconcile and supervisor paths rather than relying on a controller shell
- carry the already-live ADR 0226 host control-loop baseline into the latest `origin/main` integration candidate
- update ADR-local, workstream-local, receipt, and protected integration truth so another agent can audit the result without hidden context

## Expected Repo Surfaces

- `docs/adr/0224-server-resident-operations-as-the-default-control-model.md`
- `docs/adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0224-live-apply.md`
- `docs/workstreams/ws-0226-live-apply.md`
- `docs/runbooks/server-resident-reconciliation.md`
- `docs/runbooks/configure-host-control-loops.md`
- `receipts/live-applies/`
- `workstreams.yaml`
- protected integration files only if this branch becomes the final verified merge-to-main step

## Expected Live Surfaces

- `proxmox_florin` keeps the trusted server-resident checkout, `lv3-server-resident-reconciliation.timer`, and host-local reconciliation receipts active from the private Gitea source
- `proxmox_florin` keeps the canonical ADR 0226 `systemd` service, timer, and path units active with durable status under `/var/lib/lv3-host-control-loops/`
- the current mainline control model can be evidenced through server-resident host execution, server-side validation, and host-local secret/runtime supervision without depending on an open Codex session

## Verification

- `uv run --with pytest pytest -q tests/test_proxmox_host_control_loops_role.py tests/test_server_resident_reconciliation.py`
- `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json role-argument-specs ansible-syntax data-models`
- exact-main replay of the private Gitea source followed by `systemctl start lv3-server-resident-reconciliation.service`
- exact-main replay of `make configure-host-control-loops`
- host verification of `lv3-host-control-loop-reconcile.service`, `.timer`, and `.path`

## Notes For The Next Assistant

- keep this workstream `in_progress` until the exact-main replay and final branch validation are complete; the terminal status flip belongs at the end of the verified integration step
- the host trusts the private Gitea repo rather than GitHub directly, so the final proof must publish the integrated candidate into the private Gitea source before replaying the server-resident pull path
