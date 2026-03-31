# Workstream ws-0304-live-apply: Live Apply ADR 0304 From Latest `origin/main`

- ADR: [ADR 0304](../adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md)
- Title: Verify Atlas schema linting, snapshot refresh, and Windmill drift detection from the latest realistic `origin/main` baseline
- Status: in_progress
- Latest `origin/main`: `bb94f851a3398daaceb8348280afdd4adb6815d1`
- Latest `origin/main` Repo Version: `0.177.113`
- Branch: `codex/ws-0304-mainline`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0304-mainline`
- Owner: codex
- Depends On: `adr-0043`, `adr-0044`, `adr-0077`, `adr-0087`, `adr-0228`, `adr-0269`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0304-live-apply.md`, `docs/adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md`, `docs/runbooks/configure-atlas.md`, `docs/adr/.index.yaml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`, `playbooks/openbao.yml`, `playbooks/tasks/openbao-refresh-approle-artifact.yml`, `tests/test_compose_runtime_secret_injection.py`, `tests/test_openbao_compose_env_helper.py`, `tests/test_openbao_runtime_role.py`, `tests/test_openbao_systemd_credentials_helper.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/atlas-drift/`, `receipts/live-applies/`

## Scope

- land the live-apply hardening needed for ADR 0304 on the latest realistic
  `origin/main` baseline without rewriting protected release surfaces before the
  final exact-main integration step
- replay the repo-managed OpenBao and Windmill paths until Atlas dynamic
  credentials, snapshot refresh, and the seeded `f/lv3/atlas_drift_check`
  verification all pass end to end
- leave receipts, ADR metadata, and workstream state in a shape another agent
  can merge safely even if shared-host contention delays the final replay

## Current State

- Branch commit `3ae16236c` captures the current fix set:
  - OpenBao now reconciles database backend `allowed_roles` after role upserts
  - controller-local AppRole artifact refresh now retries one role at a time
    after re-unsealing OpenBao
  - Windmill now remirrors `scripts/atlas_schema.py`,
    `scripts/run_python_with_packages.sh`, and `config/atlas/` immediately
    before Atlas verification and asserts the guest-side checksums match the
    controller workspace
  - the compose and systemd OpenBao helper paths now wait for `status == 200`
    and `sealed == false` before secret delivery continues
- Focused repo proof is already clean on this branch:
  - `uv run --with pytest pytest tests/test_atlas_schema.py tests/test_atlas_drift_check_windmill.py tests/test_parallel_check.py tests/test_validation_gate.py tests/test_openbao_compose_env_helper.py tests/test_openbao_systemd_credentials_helper.py tests/test_compose_runtime_secret_injection.py tests/test_openbao_runtime_role.py tests/test_openbao_postgres_backend_role.py tests/test_windmill_default_operations_surface.py tests/test_windmill_operator_admin_app.py -q`
    returned `100 passed in 6.90s`
  - `make atlas-validate` returned `status: ok`
  - `make atlas-lint` returned `status: ok`
- The current live blocker is reproduced and diagnosed:
  - `make atlas-refresh-snapshots` currently fails with `HTTP Error 500`
  - the staged diagnostic in
    `receipts/live-applies/evidence/2026-03-31-adr-0304-openbao-dynamic-creds-error-r1.txt`
    shows OpenBao AppRole login succeeds but
    `GET /v1/database/creds/postgres-atlas-readonly` returns
    `"postgres-atlas-readonly" is not an allowed role`
- The remaining live replays are intentionally waiting for a safe shared-host
  window because multiple other workstreams are actively mutating
  `docker-runtime-lv3` and `postgres-lv3`

## Verification So Far

- `receipts/live-applies/evidence/2026-03-31-adr-0304-targeted-checks-r1.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-validate-r1.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-lint-r1.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-refresh-snapshots-r1.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-snapshot-probe-r1.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-snapshot-diagnose-r1.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-openbao-dynamic-creds-error-r1.txt`

## Remaining Before Merge-To-Main

- rerun `make converge-openbao` from this worktree after the shared runtime
  hosts clear, then confirm `postgres-atlas-readonly` can mint dynamic
  credentials again
- rerun `make atlas-refresh-snapshots` and `make atlas-drift-check`
- replay the governed Windmill verification from this worktree and confirm the
  seeded `f/lv3/atlas_drift_check` script returns `status: ok` and
  `report.status: clean`
- update ADR 0304 metadata, the ADR index, and the final branch-local
  live-apply receipt once the live proof is complete
- rebase onto the latest `origin/main`, run the final repo validation and
  release-management paths, then update protected `main`-only files as part of
  the exact-main integration
