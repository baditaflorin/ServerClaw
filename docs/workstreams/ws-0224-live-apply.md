# Workstream WS-0224: Server-Resident Operations Default-Control Live Apply

- ADR: [ADR 0224](../adr/0224-server-resident-operations-as-the-default-control-model.md)
- Title: Verify and integrate the default server-resident control model from the latest `origin/main`
- Status: live_applied
- Implemented In Repo Version: 0.177.48
- Live Applied In Platform Version: 0.130.42
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0224-live-apply-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0224-live-apply-r3`
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

- `uv run --with pytest pytest -q tests/test_proxmox_host_control_loops_role.py tests/test_server_resident_reconciliation.py` passed with `10 passed in 0.09s`, and `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json role-argument-specs ansible-syntax data-models` passed on the active validation commit `7b4462fe17c4bcf1bc458a2dea4e261c86104e11`.
- Private Gitea accepted branch head `8b6db7e83aef863792da7e8cf99a4e59b8286c07`; workflow run `56` / run number `52` finished with `status: completed` and `conclusion: success`, and job `70` named `validate` ran on runner `docker-build-lv3`.
- Private Gitea `main` fast-forwarded from `5b121f700d0f1cd372ef85f24288691fb8a88e0c` to snapshot `64417a8866bcc103ea3b5815359a6e5027504831` published for source commit `8b6db7e83aef863792da7e8cf99a4e59b8286c07`; the same remote gate passed `alert-rule-validation`, `ansible-lint`, `ansible-syntax`, `artifact-secret-scan`, `dependency-direction`, `dependency-graph`, `integration-tests`, `packer-validate`, `schema-validation`, `security-scan`, `service-completeness`, `tofu-validate`, `type-check`, and `yaml-lint`.
- `sudo systemctl start lv3-server-resident-reconciliation.service` completed successfully on `proxmox_florin`; `/srv/proxmox_florin_server` checked out `64417a8866bcc103ea3b5815359a6e5027504831`, the working tree stayed clean, and `/var/lib/lv3/server-resident-reconciliation/receipts/latest.json` recorded `status: ok`, `exit_code: 0`, `duration_seconds: 12`, and `source_commit: 64417a8866bcc103ea3b5815359a6e5027504831`.
- Writing `ws-0224-path-20260328T201750Z` to `/var/lib/lv3-host-control-loops/requests/reconcile.request` was consumed immediately; `latest.json` recorded `trigger: path_request` at `2026-03-28T20:17:51Z` with history file `/var/lib/lv3-host-control-loops/runs/20260328T201751Z.json`.
- `sudo systemctl start lv3-host-control-loop-reconcile.service` immediately after the exact-main replay recorded `trigger: scheduled_or_manual` at `2026-03-28T20:17:59Z`; the service finished `Result=success ActiveState=inactive`, and both the timer and path units remained `active/waiting`.

## Outcome

- Release `0.177.48` records ADR 0224 as implemented in repository truth and platform version `0.130.42` as the first exact-main proof that routine reconciliation, validation, and bounded host execution no longer depend on an open Codex session.
- ADR 0226 is now integrated into the same repository release while the first-live host-control-loop platform version remains `0.130.38`.
- The exact-main host replay used source commit `8b6db7e83aef863792da7e8cf99a4e59b8286c07` via private Gitea snapshot `64417a8866bcc103ea3b5815359a6e5027504831`; the remaining same-turn branch edits after that replay are ADR-local metadata, release truth, and receipt surfaces only.
