# Workstream WS-0373: Service Registry Live Apply

- ADR: [ADR 0373](../adr/0373-service-registry-and-derived-defaults.md)
- Title: Service Registry and Derived Defaults
- Status: ready
- Branch: `codex/ws-0373-live-apply`
- Worktree: `.worktrees/ws-0373-live-apply`
- Owner: `codex`
- Depends On: `adr-0344-single-source-environment-topology`, `adr-0359-declarative-postgresql-client-registry`
- Conflicts With: none
- Shared Surfaces: `inventory/group_vars/all/platform_services.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/derive_service_defaults.yml`, `scripts/validate_service_registry.py`, `docs/adr/0373-service-registry-and-derived-defaults.md`, `docs/runbooks/add-new-service-to-platform.md`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- validate the latest `origin/main` ADR 0373 codepath from an isolated worktree
- replay the governed production live-apply path for the service-registry pattern
- verify representative current-platform services and automation paths end to end
- leave merge-safe evidence and metadata even though ADR 0407 removed `receipts/` from the default committed surface

## Non-Goals

- re-implementing ADR 0373 from scratch when the code is already merged on `origin/main`
- bumping `VERSION`, editing release sections in `changelog.md`, or changing the top-level `README.md` summary before final integration on `main`
- broad unrelated platform changes outside the service-registry/defaults contract

## Expected Repo Surfaces

- `workstreams/active/ws-0373-live-apply.yaml`
- `docs/workstreams/ws-0373-live-apply.md`
- `docs/adr/0373-service-registry-and-derived-defaults.md`
- `docs/adr/implementation-status/adr-0373.yaml`
- `docs/postmortems/adr-0373-service-registry-adoption-completion.md`
- `docs/runbooks/add-new-service-to-platform.md`
- `inventory/group_vars/all/platform_services.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/derive_service_defaults.yml`
- `scripts/validate_service_registry.py`
- `scripts/validate_repo.sh`
- `tests/test_validate_service_completeness.py`
- `tests/test_ansible_execution_scopes.py`
- `workstreams.yaml`
- `receipts/live-applies/`

## Expected Live Surfaces

- the current production converge path can apply latest-main ADR 0373 state without undefined-variable regressions
- representative live services across the current platform still derive conventional defaults correctly from the registry
- repo automation and validation entrypoints that guard ADR 0373 remain green from the isolated worktree

## Verification

- Repo preparation and refresh completed from latest `origin/main` (`bbdb0f700`).
- Passed:
  - `python3 scripts/validate_service_registry.py --check`
  - `python3 scripts/interface_contracts.py --list`
  - `./scripts/validate_repo.sh agent-standards`
  - `uv run --with pytest --with pyyaml --with fastapi --with jinja2 --with python-multipart --with itsdangerous --with httpx python -m pytest -q tests/test_openbao_systemd_credentials_helper.py tests/test_restic_config_backup.py tests/test_docker_runtime_role.py tests/test_common_docker_bridge_chains_helper.py tests/test_linux_guest_firewall_role.py`
  - earlier targeted latest-main regression sweep:
    - `tests/test_security_posture_report.py`
    - `tests/test_maintenance_window_tool.py`
    - `tests/test_governed_command.py`
    - `tests/test_platform_observation_tool.py`
    - `tests/test_restore_verification.py`
    - `tests/test_generate_platform_vars.py::test_build_platform_vars_resolves_guest_ip_templates_in_platform_host_network`
  - `make preflight WORKFLOW=live-apply-service`

## Live Apply Outcome

- completed on 2026-04-13 after the controller-to-runtime access path recovered
- representative ADR 0373 latest-main replay succeeded for both the governed
  backup path and the production `repo_intake` service entrypoint
- remaining work for merge-to-main is integration-only:
  - merge the branch onto `main`
  - replay the same service from the merged `main` tree
  - update protected integration files (`VERSION`, `changelog.md`,
    `versions/stack.yaml`, `README.md`, generated release docs)

## Live Evidence

- Latest-main repair surface kept on this branch:
  - `platform/interface_contracts.py`
  - `config/workflow-catalog.json`
  - `playbooks/services/repo_intake.yml`
  - `scripts/trigger_restic_live_apply.py`
  - `scripts/drift_lib.py`
  - `scripts/governed_command.py`
  - `scripts/platform_observation_tool.py`
  - `scripts/maintenance_window_tool.py`
  - `scripts/restore_verification.py`
  - Docker/OpenBao helper fixes under
    `collections/ansible_collections/lv3/platform/roles/`
- Restic replay:
  - `LV3_PROXMOX_HOST_ADDR=65.108.75.123 LV3_PROXMOX_HOST_PORT=2222 make converge-restic-config-backup env=production`
    completed successfully and refreshed the runtime password state
  - `LV3_PROXMOX_HOST_ADDR=65.108.75.123 LV3_PROXMOX_HOST_PORT=2222 python3 scripts/trigger_restic_live_apply.py --env production --mode backup --triggered-by ws-0373-live-apply --live-apply-trigger`
    returned `status=ok`
  - receipts refreshed:
    - `receipts/restic-backups/20260413T105157Z.json`
    - `receipts/restic-backups/20260413T110651Z.json`
    - `receipts/restic-snapshots-latest.json`
- `repo_intake` replay:
  - `LV3_PROXMOX_HOST_ADDR=65.108.75.123 LV3_PROXMOX_HOST_PORT=2222 make live-apply-service service=repo_intake env=production ALLOW_IN_PLACE_MUTATION=true`
    completed with `failed=0`
  - `docker-runtime` verification:
    - `docker ps` shows `repo-intake` healthy and publishing `0.0.0.0:8101->8101/tcp`
    - `curl http://127.0.0.1:8101/health` returned `{"status":"ok"}`
    - the root page served the expected `Repo Intake — LV3` HTML
  - edge verification from `nginx`:
    - `curl -kfsS --resolve repo-intake.lv3.org:443:127.0.0.1 https://repo-intake.lv3.org/health`
      returned the expected `HTTP/2 302` OAuth redirect
    - `curl -kfsS --resolve repo-intake.lv3.org:443:127.0.0.1 https://repo-intake.lv3.org/`
      returned the same authenticated edge behavior
- Supporting historical evidence remains in
  `receipts/live-applies/2026-04-09-adr-0373-phases5-6-100pct-adoption-live-apply.json`,
  which is the first platform receipt claiming 100% ADR 0373 adoption.

## Mainline Integration Notes

- protected integration files remain intentionally uncommitted on this branch
- the merge-to-main step must regenerate canonical truth from the merged tree
  before cutting the next release and updating `versions/stack.yaml`
