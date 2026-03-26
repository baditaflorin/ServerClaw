# Workstream WS-0108: Operator Onboarding and Off-boarding Live Apply

- ADR: [ADR 0108](../adr/0108-operator-onboarding-and-offboarding.md)
- Title: Live apply and end-to-end verification for the Windmill-backed operator onboarding and off-boarding workflow
- Status: live_applied
- Implemented In Repo Version: 0.174.0
- Live Applied In Platform Version: 0.130.20
- Implemented On: 2026-03-26
- Live Applied On: 2026-03-26
- Branch: `codex/ws-0108-live-apply`
- Worktree: `.worktrees/ws-0108-live-apply`
- Owner: codex
- Depends On: `adr-0042-step-ca`, `adr-0043-openbao`, `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0122-operator-access-admin`
- Conflicts With: none
- Shared Surfaces: `scripts/operator_manager.py`, `config/windmill/scripts/`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `docs/runbooks/operator-onboarding.md`, `docs/runbooks/operator-offboarding.md`, `docs/runbooks/configure-windmill.md`, `tests/test_operator_manager.py`, `tests/test_windmill_operator_admin_app.py`, `tests/test_config_merge_windmill.py`, `tests/test_config_merge_repo_surfaces.py`

## Scope

- finish the ADR 0108 browser-first live path from the latest `origin/main` in an isolated worktree and branch
- make the Windmill worker runtime carry the operator-manager env passthrough, bootstrap secret mirrors, writable checkout paths, and schedule sync helper needed by the repo-managed scripts
- make the Windmill wrappers robust to runtime-env injection and command ordering so they execute the repo-managed operator workflow consistently
- verify the repo validation path and the live Windmill operator lifecycle path end to end without touching protected integration files on the branch
- leave branch-local evidence and merge guidance so another assistant can integrate safely on `main`

## Verification

- `uv run --with pytest pytest -q tests/test_operator_manager.py tests/test_windmill_operator_admin_app.py tests/test_config_merge_windmill.py tests/test_config_merge_repo_surfaces.py` passed with `33 passed in 0.33s`
- `python3 -m py_compile scripts/operator_manager.py scripts/sync_windmill_seed_scripts.py scripts/sync_windmill_seed_schedules.py config/windmill/scripts/operator-onboard.py config/windmill/scripts/operator-offboard.py config/windmill/scripts/operator-inventory.py config/windmill/scripts/operator-roster.py config/windmill/scripts/sync-operators.py config/windmill/scripts/quarterly-access-review.py` passed
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, `make syntax-check-windmill`, `make workflow-info WORKFLOW=converge-windmill`, `make workflow-info WORKFLOW=operator-onboard`, `make workflow-info WORKFLOW=operator-offboard`, and `make workflow-info WORKFLOW=quarterly-access-review` all passed
- `make converge-windmill` completed successfully from this worktree after the final runtime-role changes with `docker-runtime-lv3 : ok=170 changed=29 failed=0`, `postgres-lv3 : ok=57 changed=1 failed=0`, and `proxmox_florin : ok=36 changed=4 failed=0`
- Windmill live run `operator_onboard` succeeded for temporary operator `codex-live-apply-0108` with Keycloak user `fef7292c-dcc2-4517-b8a7-6425b0bff264`, OpenBao entity `be7bb5b4-7227-54d9-159e-71c45da447ff`, audit timestamp `2026-03-26T17:13:20Z`, state file `/srv/proxmox_florin_server/.local/state/operator-access/codex-live-apply-0108.json`, and roster file `/srv/proxmox_florin_server/config/operators.yaml`
- Windmill live `operator_inventory` confirmed the temporary operator as active in Keycloak and OpenBao immediately after onboarding
- Windmill live run `operator_offboard` succeeded for `codex-live-apply-0108` at audit timestamp `2026-03-26T17:13:35Z`
- Post-offboard `operator_inventory` confirmed `keycloak.status=disabled`, `openbao.status=disabled`, and the roster status `inactive`
- Post-converge worker verification confirmed `windmill-windmill_worker-1` is attached to both `windmill_default` and `openbao_default`, resolves `lv3-openbao` to `172.20.0.2`, returns an initialized and unsealed health payload from `curl http://lv3-openbao:8201/v1/sys/health`, and exposes `LV3_OPENBAO_URL=http://lv3-openbao:8201` in the live worker container environment
- A second Windmill live round-trip after the automated converge succeeded for `codex-live-apply-0108-postconverge`: onboarding completed at `2026-03-26T17:28:23Z`, inventory confirmed Keycloak `active` plus OpenBao `active`, offboarding completed at `2026-03-26T17:28:25Z`, and the final inventory confirmed Keycloak `disabled`, OpenBao `disabled`, and operator status `inactive`

## Outcome

- the repo now encodes the Windmill-worker persistence needed for ADR 0108: retry-aware seed sync, operator-manager env passthrough, mirrored bootstrap secrets, writable worker checkout paths, and explicit worker attachment to the external OpenBao Docker network
- the browser-first Windmill path is live-verified end to end for onboarding, inventory, offboarding, and post-offboard inventory against the current production platform
- optional integrations remain graceful in the verified live path: Tailscale and Mattermost report as skipped when their runtime env is absent, and viewer-role step-ca access remains disabled by design

## Temporary Live Assertions During Verification

- attached `windmill-windmill_worker-1` and `windmill-windmill_worker_native-1` directly to `openbao_default` with `docker network connect` during early live debugging before the final repo-managed `make converge-windmill`; the successful post-converge verification shows the network attachment is now durable from the committed compose contract
- updated `/run/lv3-secrets/windmill/runtime.env` in place during early live debugging; after the final repo-managed converge the worker container environment itself exposes `LV3_OPENBAO_URL=http://lv3-openbao:8201`, which is the value inherited by the Windmill wrapper subprocesses
- asserted live worker checkout mutability directly on `/srv/proxmox_florin_server/config/operators.yaml` and `/srv/proxmox_florin_server/.local/state/operator-access`
- mirrored `/srv/proxmox_florin_server/.local/keycloak/bootstrap-admin-password.txt` and `/srv/proxmox_florin_server/.local/openbao/init.json` into the worker checkout during live iteration
- copied the latest repo `scripts/operator_manager.py` into `/srv/proxmox_florin_server/scripts/operator_manager.py` during live iteration

## Merge-To-Main Follow-Up

- do not update `VERSION` on this branch; bump it only when this work is merged on `main`
- do not update release sections in `changelog.md` on this branch
- do not update the top-level `README.md` integrated status summary on this branch
- do not update `versions/stack.yaml` on this branch even though the live verification used platform version `0.130.20`
- a clean `main` integration should replay the current repo-managed `converge-windmill` path so the temporary direct live assertions are replaced by durable managed state
