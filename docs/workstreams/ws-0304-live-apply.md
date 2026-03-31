# Workstream ws-0304-live-apply: Live Apply ADR 0304 From Latest `origin/main`

- ADR: [ADR 0304](../adr/0304-atlas-for-declarative-database-schema-migration-versioning-and-pre-migration-linting.md)
- Title: Verify Atlas schema linting, snapshot refresh, and Windmill drift detection from the latest realistic `origin/main` baseline
- Status: in_progress
- Latest `origin/main`: `24214be7347227612051af0f8c1080f114c45402`
- Latest `origin/main` Repo Version: `0.177.122`
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

- The branch now carries the full ADR 0304 hardening set needed for live apply:
  - `scripts/atlas_schema.py` now validates the declared NATS subject against
    the active taxonomy, normalizes trailing whitespace in inspected HCL
    snapshots, prefers runtime-provided OpenBao and ntfy secrets when present,
    and can recover a sealed OpenBao instance through the managed init payload
    before the Atlas AppRole login
  - the OpenBao runtime and helper tasks now wait for the cluster to be
    unsealed before continuing secret delivery and refresh the controller-local
    Atlas AppRole artifact through the managed path
  - the Windmill runtime contract now injects
    `LV3_ATLAS_OPENBAO_APPROLE_JSON` and
    `LV3_NTFY_ALERTMANAGER_PASSWORD`, asserts those values exist both in the
    rendered runtime env and in the live worker container, and copies the
    controller-local secret artifacts into the isolated checkout with stable
    ownership
  - `config/windmill/scripts/atlas-drift-check.py` now self-hydrates the Atlas
    AppRole JSON and ntfy password from the repo-local `.local/` artifacts when
    the worker subprocess environment drops those variables, so the seeded
    Windmill script still runs from the isolated checkout
  - the repo-managed Windmill raw-app sync path now checks the Windmill API and
    will restart the minimal compose subset before `wmill sync push` if another
    concurrent playbook has cleanly stopped the stack
- Focused repo proof is clean on the current branch tip:
  - `uv run --with pytest pytest tests/test_atlas_schema.py tests/test_atlas_drift_check_windmill.py tests/test_windmill_operator_admin_app.py tests/test_openbao_compose_env_helper.py tests/test_openbao_runtime_role.py tests/test_compose_runtime_secret_injection.py tests/test_openbao_systemd_credentials_helper.py -q`
    returned `88 passed in 1.05s`
  - `./scripts/validate_repo.sh agent-standards` passed
  - earlier branch-local validation also passed for `make atlas-validate`,
    `make atlas-lint`, and
    `uv run --with pyyaml python scripts/validate_nats_topics.py --validate`
- Live proof has progressed materially:
  - `make converge-openbao` succeeded and the Atlas AppRole now mints the
    `postgres-atlas-readonly` dynamic credential again
  - `make atlas-drift-check` returned a clean report with `drift_count: 0`
    and no published notifications
  - the governed Windmill job failure was reproduced, diagnosed, and fixed: the
    worker wrapper previously lost the Atlas AppRole artifact when the job
    subprocess env was narrowed, and later the raw-app sync failed because
    another playbook had stopped the Windmill stack between checks
- The remaining blocker is shared-host contention rather than an uncovered ADR
  0304 bug. Multiple other workstreams are still actively mutating
  `docker-runtime-lv3`, `proxmox_florin`, `postgres-lv3`, and `nginx-lv3`, so
  the final `make converge-windmill env=production` replay is waiting for a
  safer window before the exact end-to-end verification is retried.

## Verification So Far

- `receipts/live-applies/evidence/2026-03-31-adr-0304-converge-openbao-r6.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-drift-check-r6.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-drift-check-job-inspect-r3.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-converge-windmill-r16.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-targeted-checks-r1.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-validate-r1.txt`
- `receipts/live-applies/evidence/2026-03-31-adr-0304-atlas-lint-r1.txt`

## Remaining Before Merge-To-Main

- wait for a safe shared-host window, then rerun
  `make converge-windmill env=production` from this worktree and capture a new
  receipt proving the raw-app sync survives transient Windmill downtime
- rerun the governed Windmill verification and confirm
  `f/lv3/atlas_drift_check` returns `status: ok` with `report.status: clean`
- rerun the final repo validation path from the post-live branch tip and record
  the fresh evidence used for merge
- update ADR 0304 metadata, regenerate `docs/adr/.index.yaml`, and mark
  `workstreams.yaml` ready-to-merge once the live proof is complete
- refresh onto the latest `origin/main`, then update the protected `main`-only
  files as part of the exact-main integration before merging and pushing
