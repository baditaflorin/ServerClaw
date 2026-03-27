# Workstream WS-0108: Operator Onboarding and Off-boarding Live Apply

- ADR: [ADR 0108](../adr/0108-operator-onboarding-and-offboarding.md)
- Title: Live apply and end-to-end verification for the Windmill-backed operator onboarding and off-boarding workflow
- Status: live_applied
- Implemented In Repo Version: 0.177.8
- Live Applied In Platform Version: 0.130.29
- Implemented On: 2026-03-27
- Live Applied On: 2026-03-27
- Branch: `codex/ws-0108-main-merge-v5`
- Worktree: `.worktrees/ws-0108-main-merge`
- Owner: codex
- Depends On: `adr-0042-step-ca`, `adr-0043-openbao`, `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0122-operator-access-admin`
- Conflicts With: none
- Shared Surfaces: `scripts/operator_manager.py`, `config/windmill/scripts/`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `docs/runbooks/operator-onboarding.md`, `docs/runbooks/operator-offboarding.md`, `docs/runbooks/configure-windmill.md`, `tests/test_operator_manager.py`, `tests/test_windmill_operator_admin_app.py`, `tests/test_config_merge_windmill.py`, `tests/test_config_merge_repo_surfaces.py`

## Scope

- replay ADR 0108 from the latest `origin/main` in an isolated worktree and branch suitable for concurrent agent work
- harden the Windmill worker runtime so the repo-managed operator workflows inherit the required env passthrough, mirrored bootstrap secrets, writable checkout paths, and resilient seed sync behavior
- verify the repo validation path plus the live Windmill operator lifecycle path end to end on the freshly converged production platform
- complete the protected integration step on `main`, including release metadata, canonical platform state, and the structured live-apply receipt

## Verification

- `uv run --with pytest pytest -q tests/test_config_merge_windmill.py tests/test_run_namespace.py tests/test_ansible_execution_scopes.py tests/test_windmill_operator_admin_app.py tests/test_docker_runtime_role.py tests/test_operator_manager.py tests/test_config_merge_repo_surfaces.py tests/test_ephemeral_lifecycle_repo_surfaces.py` passed with `52 passed in 0.76s`
- `python3 -m py_compile scripts/operator_manager.py scripts/run_namespace.py scripts/sync_windmill_seed_scripts.py scripts/sync_windmill_seed_schedules.py config/windmill/scripts/operator-onboard.py config/windmill/scripts/operator-offboard.py config/windmill/scripts/operator-inventory.py config/windmill/scripts/quarterly-access-review.py` passed
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, `make syntax-check-windmill`, `make workflow-info WORKFLOW=converge-windmill`, `make workflow-info WORKFLOW=operator-onboard`, `make workflow-info WORKFLOW=operator-offboard`, and `make workflow-info WORKFLOW=quarterly-access-review` all passed on the final integration branch
- `git fetch origin --prune` confirmed the integration branch remained `ahead 3` and `behind 0` relative to `origin/main` before cutting the final mainline release step
- `make converge-windmill` completed successfully from this worktree on the latest `origin/main` replay with `docker-runtime-lv3 : ok=203 changed=37 failed=0`, `postgres-lv3 : ok=63 changed=1 failed=0`, and `proxmox_florin : ok=36 changed=4 failed=0`
- Live worker verification confirmed `windmill-windmill_worker-1` is attached to both `windmill_default` and `openbao_default`, exposes `LV3_OPERATOR_MANAGER_SURFACE=windmill` plus `LV3_OPENBAO_URL=http://lv3-openbao:8201`, resolves `lv3-openbao` to `172.20.0.2`, and returns an initialized and unsealed health payload from `curl http://lv3-openbao:8201/v1/sys/health`
- Windmill API verification confirmed `GET /api/version` returned `CE v1.662.0`, `GET /api/users/whoami` returned `superadmin_secret@windmill.dev`, and schedule `f/lv3/quarterly_access_review_every_monday_0900` remained enabled with cron `0 0 9 * * 1` in timezone `Europe/Bucharest`
- Windmill live round-trip `codex-mainline-0108-raw-20260327t1200z` succeeded end to end: onboarding completed at `2026-03-27T12:00:31Z`, created Keycloak user `b083aa43-0c93-4199-98d0-dfa891896f06`, created OpenBao entity `3a3bfd44-fdc6-f879-fd02-c8ecffd9b32b`, active inventory showed Keycloak `active`, OpenBao `active`, and roster status `active`, offboarding completed at `2026-03-27T12:00:32Z`, and final inventory showed Keycloak `disabled`, OpenBao `disabled`, and roster status `inactive`
- Optional integrations remained graceful in the verified live path: step-ca register and revoke stayed `skipped`, Tailscale invite and removal stayed `skipped` or `unavailable`, and Mattermost notifications stayed `skipped` when their runtime environment variables were absent

## Outcome

- the repo now carries the latest-main ADR 0108 durability fixes for Windmill seed sync retries, worker env passthrough, mirrored bootstrap secrets, writable checkout paths, and worker access to the external OpenBao Docker network
- the browser-first Windmill path is verified end to end on production from the latest mainline replay for onboarding, inventory, offboarding, and post-offboard inventory
- the final mainline release records both the repo-side integration and the verified live state, so another assistant can merge and reason from `main` without consulting branch-local context

## Mainline Integration

- this workstream now records the final latest-main live apply that was verified from the isolated integration worktree and then merged on `main`
- the structured receipt for this replay is `2026-03-27-adr-0108-operator-onboarding-mainline-live-apply`
- no additional merge-to-main cleanup is required beyond the normal push and optional future configuration of the step-ca, Tailscale, and Mattermost hooks
