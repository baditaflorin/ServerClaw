# Workstream WS-0224: Server-Resident Operations Default-Control Live Apply

- ADR: [ADR 0224](../adr/0224-server-resident-operations-as-the-default-control-model.md)
- Title: Verify and integrate the default server-resident control model from the latest `origin/main`
- Status: live_applied
- Implemented In Repo Version: 0.177.52
- Live Applied In Platform Version: 0.130.42
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0224-live-apply-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0224-live-apply-r3`
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

- `proxmox-host` keeps the trusted server-resident checkout, `lv3-server-resident-reconciliation.timer`, and host-local reconciliation receipts active from the private Gitea source
- `proxmox-host` keeps the canonical ADR 0226 `systemd` service, timer, and path units active with durable status under `/var/lib/lv3-host-control-loops/`
- the current mainline control model can be evidenced through server-resident host execution, server-side validation, and host-local secret/runtime supervision without depending on an open Codex session

## Verification

- Candidate commit `14143f58d6ef38dbfb709d74ff315531c6900571` passed the focused local integration suite: `uv run --with pytest --with jinja2 --with jsonschema pytest -q tests/test_proxmox_host_control_loops_role.py tests/test_server_resident_reconciliation.py tests/test_policy_checks.py tests/test_command_catalog.py tests/test_parallel_check.py tests/test_promotion_pipeline.py tests/test_windmill_operator_admin_app.py tests/test_release_manager.py tests/test_canonical_truth.py tests/test_docs_site.py tests/test_validate_repo_cache.py` returned `68 passed in 7.45s`, `./scripts/validate_repo.sh agent-standards yaml json role-argument-specs ansible-syntax data-models` passed, `scripts/live_apply_receipts.py --validate`, `scripts/generate_adr_index.py --check`, `scripts/canonical_truth.py --check`, `scripts/platform_manifest.py --check`, `scripts/generate_diagrams.py --check`, and `git diff --check` all passed, and `make pre-push-gate` completed successfully with `alert-rule-validation`, `ansible-lint`, `ansible-syntax`, `artifact-secret-scan`, `dependency-direction`, `dependency-graph`, `integration-tests`, `packer-validate`, `policy-validation`, `schema-validation`, `security-scan`, `service-completeness`, `tofu-validate`, `type-check`, and `yaml-lint`.
- Private Gitea accepted branch head `14143f58d6ef38dbfb709d74ff315531c6900571`; workflow run `66` (API id `70`) finished with `status: completed` and `conclusion: success`, and job `88` named `validate` ran on runner `docker-build` from `2026-03-28T21:11:34Z` through `2026-03-28T21:11:37Z`.
- Private Gitea `main` fast-forwarded from `c3ef5f172c7ec178a692b0ee772d2d1349096ab5` to snapshot `9f988bf58f6f02c4add3c6292c65fbed929edac9` published for source commit `14143f58d6ef38dbfb709d74ff315531c6900571`; workflow run `67` (API id `71`) finished with `status: completed` and `conclusion: success`, and job `89` named `validate` ran on runner `docker-build` from `2026-03-28T21:12:30Z` through `2026-03-28T21:12:34Z`.
- `sudo systemctl start lv3-server-resident-reconciliation.service` completed successfully on `proxmox-host`; `/srv/proxmox-host_server` checked out `9f988bf58f6f02c4add3c6292c65fbed929edac9`, the working tree stayed clean, and `/var/lib/lv3/server-resident-reconciliation/receipts/latest.json` recorded `status: ok`, `exit_code: 0`, `duration_seconds: 12`, `started_at: 2026-03-28T21:12:55Z`, `finished_at: 2026-03-28T21:13:07Z`, and `source_commit: 9f988bf58f6f02c4add3c6292c65fbed929edac9`.
- Writing `ws-0224-path-20260328T211342Z` to `/var/lib/lv3-host-control-loops/requests/reconcile.request` was consumed immediately; `/var/lib/lv3-host-control-loops/status/latest.json` recorded `trigger: path_request` at `2026-03-28T21:13:42Z` with history file `/var/lib/lv3-host-control-loops/runs/20260328T211342Z.json`.
- `sudo systemctl start lv3-host-control-loop-reconcile.service` immediately after the exact-main replay recorded `trigger: scheduled_or_manual` at `2026-03-28T21:13:52Z` with history file `/var/lib/lv3-host-control-loops/runs/20260328T211352Z.json`; the service finished `Result=success ExecMainStatus=0 ActiveState=inactive SubState=dead`, and both the timer and path units remained `ActiveState=active SubState=waiting`.

## Outcome

- Release `0.177.52` records ADR 0224 as implemented in repository truth and platform version `0.130.42` as the first exact-main proof that routine reconciliation, validation, and bounded host execution no longer depend on an open Codex session.
- ADR 0226 is now integrated into the same repository release while the first-live host-control-loop platform version remains `0.130.38`.
- The exact-main host replay used source commit `14143f58d6ef38dbfb709d74ff315531c6900571` via private Gitea snapshot `9f988bf58f6f02c4add3c6292c65fbed929edac9`; the remaining same-turn branch edits after that replay are ADR-local metadata, release truth, and receipt surfaces only.
