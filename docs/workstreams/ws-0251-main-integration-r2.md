# Workstream ws-0251-main-integration-r2

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Integrate ADR 0251 latest-server-state follow-up onto `origin/main`
- Status: `in_progress`
- Target Repo Version: 0.177.92
- Target Platform Version: 0.130.61
- Release Date: 2026-03-29
- Branch: `codex/ws-0251-main-integration-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0251-live-apply`
- Owner: codex
- Depends On: `ws-0251-live-apply`, `ws-0251-main-integration`

## Purpose

Carry the already-validated ADR 0251 follow-up onto the latest `origin/main`
baseline, cut the next patch release for the protected integration surfaces,
replay the merged OpenBao and Windmill verification from the exact future main
commit, and publish one structured receipt that records the latest realistic
server state for the promotion-gate, stage-smoke, OpenBao recovery, and
step-ca durability paths.

## Shared Surfaces

- `workstreams.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `build/platform-manifest.json`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `docs/adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md`
- `docs/workstreams/ws-0251-live-apply.md`
- `docs/workstreams/ws-0251-main-integration-r2.md`
- `docs/workstreams/adr-0043-openbao.md`
- `docs/runbooks/configure-openbao.md`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`
- `collections/ansible_collections/lv3/platform/roles/step_ca_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/step_ca_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`
- `config/windmill/scripts/gate-status.py`
- `config/windmill/scripts/stage-smoke-suites.py`
- `scripts/deployment_history.py`
- `scripts/gate_status.py`
- `scripts/live_apply_receipts.py`
- `scripts/stage_smoke_suites.py`
- `tests/test_changelog_portal.py`
- `tests/test_live_apply_receipts.py`
- `tests/test_openbao_compose_env_helper.py`
- `tests/test_openbao_runtime_role.py`
- `tests/test_compose_runtime_secret_injection.py`
- `tests/test_stage_smoke_suites.py`
- `tests/test_step_ca_runtime_role.py`
- `tests/test_validation_gate.py`
- `tests/test_validation_gate_windmill.py`
- `tests/test_windmill_integration_wrappers.py`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-29-adr-0251-*.json`
- `receipts/live-applies/evidence/2026-03-29-adr-0251-*`
- `receipts/live-applies/evidence/2026-03-29-openbao-*`

## Prepared Verification

- The integration branch inherits the validated follow-up commit
  `b6c70600b97997a1faf048d2e61014280fbdc9b4`, which already passed focused
  pytest coverage for the deployment-history portal fix and OpenBao recovery
  hardening, `./scripts/validate_repo.sh generated-vars role-argument-specs
  json alert-rules generated-docs generated-portals agent-standards`,
  `uv run --with pyyaml python3 scripts/canonical_truth.py --check`, and the
  Windmill playbook syntax check.
- Branch-local live evidence already confirms `make converge-windmill`, the
  live worker `make post-merge-gate`, post-gate `gate-status`, post-gate
  `stage-smoke-suites`, post-gate `windmill_healthcheck`, OpenBao recovery,
  and fresh host-plus-guest server-state snapshots on the latest realistic
  pre-merge baseline.
- The current integration branch is now merged onto `origin/main` release
  `0.177.91`, preserves the worker-side gate-status retry hardening, the
  latest-server-state step-ca topology recovery, and the OpenBao recovery plus
  nested-evidence receipt-enumeration fixes, and is being revalidated from
  that exact latest-main baseline before the final merge.

## Pending Exact-Main Replay

- Cut release `0.177.92` on this branch once the protected surfaces are ready,
  unless `origin/main` advances again first.
- Re-run the exact commit that will become `main` through the OpenBao and
  Windmill live paths, including a refreshed worker-local post-merge gate and
  a latest-server-state step-ca replay from the merged tip.
- Record the resulting structured receipt and then advance
  `versions/stack.yaml` to platform version `0.130.61`.
