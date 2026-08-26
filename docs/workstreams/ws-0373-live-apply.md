# Workstream WS-0373: Service Registry Live Apply

- ADR: [ADR 0373](../adr/0373-service-registry-and-derived-defaults.md)
- Title: Service Registry and Derived Defaults
- Status: merged
- Branch: `codex/ws-0373-main-closeout-r3`
- Worktree: `.worktrees/ws-0373-main-closeout-r3`
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

- `workstreams/archive/2026/ws-0373-live-apply.yaml`
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

- Repo preparation and refresh completed from latest realistic `origin/main`
  (`04638e669`, `VERSION` `0.178.148`).
- Passed:
  - `python3 scripts/validate_service_registry.py --check`
  - `python3 scripts/interface_contracts.py --list`
  - `uv run --with pytest --with pyyaml --with jsonschema --with fastapi --with jinja2 --with python-multipart --with itsdangerous --with httpx python -m pytest -q tests/test_restic_config_backup.py tests/test_repo_intake_runtime_role.py tests/test_environment_topology.py tests/test_interface_contracts.py tests/test_validate_service_registry.py tests/test_validate_service_completeness.py tests/test_ansible_execution_scopes.py`
    with `86 passed`
  - `make preflight WORKFLOW=live-apply-service`
  - `python3 scripts/vulnerability_budget.py --service repo_intake`

## Live Apply Outcome

- completed on 2026-04-21 after rebasing to the latest realistic
  `origin/main` base at `0.178.148`
- latest-main replay exposed and repaired two live regressions before the final
  rerun:
  - `repo_intake_runtime` readiness polling used the unsupported
    `connect_timeout` parameter on `ansible.builtin.uri`
  - `restic_config_backup.py` started importing `outline_client` after
    ADR 0418, but the restic runtime support bundle did not sync
    `scripts/outline_client.py` onto `docker-runtime`
- latest-main replay also refreshed the stale `docker-runtime` host security
  posture receipt before rerunning `repo_intake`, because the vulnerability
  budget gate rejected the first attempt with an 8.7-day-old host scan
- the final integrated closeout promotes this verified replay into repo and
  platform version `0.178.149`

## Live Evidence

- Latest-main replay fixes kept on this branch:
  - `collections/ansible_collections/lv3/platform/roles/repo_intake_runtime/tasks/main.yml`
  - `collections/ansible_collections/lv3/platform/roles/restic_config_backup/tasks/main.yml`
  - `scripts/trigger_restic_live_apply.py`
  - `tests/test_restic_config_backup.py`
- Restic replay:
  - `LV3_PROXMOX_HOST_ADDR=203.0.113.1 LV3_PROXMOX_HOST_PORT=2222 make converge-restic-config-backup env=production`
    completed successfully on the rebased base after syncing `outline_client.py`
  - `python3 scripts/trigger_restic_live_apply.py --env production --mode backup --triggered-by ws-0373-live-apply --live-apply-trigger`
    returned `status=ok`
  - receipts refreshed:
    - `receipts/restic-backups/20260421T105958Z.json`
    - `receipts/restic-backups/20260421T111230Z.json`
    - `receipts/restic-snapshots-latest.json`
- Security posture gate refresh:
  - `uv run --with ansible-core --with pyyaml --with nats-py python scripts/security_posture_report.py --env production --skip-trivy --audit-surface manual --print-report-json`
    re-emitted the fresh host report as
    `receipts/security-reports/20260421T110457Z.json`
  - `python3 scripts/vulnerability_budget.py --service repo_intake` returned
    `approved`
  - evidence:
    `receipts/live-applies/evidence/2026-04-21-ws-0373-mainline-vulnerability-budget-repo-intake-0.178.149.txt`
- `repo_intake` replay:
  - `ANSIBLE_COLLECTIONS_PATH="$PWD/collections:$PWD/.ansible/validation/collections" LV3_PROXMOX_HOST_ADDR=203.0.113.1 LV3_PROXMOX_HOST_PORT=2222 make live-apply-service service=repo_intake env=production ALLOW_IN_PLACE_MUTATION=true`
    completed with `failed=0`
  - the live-apply wrapper's automatic post-apply restic trigger also returned
    `status=ok`
  - `docker-runtime` verification:
    - `docker ps` shows `repo-intake` healthy and publishing `0.0.0.0:8101->8101/tcp`
    - `curl http://127.0.0.1:8101/health` returned `{"status":"ok"}`
    - the root page served the expected `Repo Intake — LV3` HTML
  - edge verification from `nginx`:
    - `curl -ksS --resolve repo-intake.example.com:443:127.0.0.1 https://repo-intake.example.com/health`
      returned the expected `HTTP/2 302` OAuth redirect
    - `curl -ksS --resolve repo-intake.example.com:443:127.0.0.1 https://repo-intake.example.com/`
      returned the same authenticated edge behavior
- Integrated closeout receipt:
  - `receipts/live-applies/2026-04-21-adr-0373-service-registry-and-derived-defaults-mainline-live-apply.json`
- Historical first-true evidence remains in
  `receipts/live-applies/2026-04-09-adr-0373-phases5-6-100pct-adoption-live-apply.json`
  as the first platform receipt claiming 100% ADR 0373 adoption.

## Mainline Integration Notes

- the archived shard records the merged state for ws-0373 and points canonical
  truth at the integrated `0.178.149` release
- the closeout refreshes `VERSION`, `RELEASE.md`, `docs/release-notes/0.178.149.md`,
  `versions/stack.yaml`, `README.md`, and the live-apply receipts so merged
  repository truth and verified platform truth describe the same state
