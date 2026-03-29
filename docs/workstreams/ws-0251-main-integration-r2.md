# Workstream ws-0251-main-integration-r2

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Integrate ADR 0251 latest-server-state follow-up onto `origin/main`
- Status: `prepared`
- Target Repo Version: 0.177.88
- Target Platform Version: 0.130.60
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
server state for the promotion-gate, stage-smoke, and OpenBao recovery paths.

## Shared Surfaces

- `workstreams.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `build/platform-manifest.json`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.88.md`
- `versions/stack.yaml`
- `docs/adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md`
- `docs/workstreams/ws-0251-live-apply.md`
- `docs/workstreams/ws-0251-main-integration-r2.md`
- `docs/runbooks/configure-openbao.md`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/tasks/main.yml`
- `scripts/deployment_history.py`
- `tests/test_changelog_portal.py`
- `tests/test_openbao_runtime_role.py`
- `receipts/live-applies/2026-03-29-adr-0251-latest-server-state-follow-up-mainline-live-apply.json`
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

## Pending Exact-Main Replay

- Cut release `0.177.88` on this branch once the protected surfaces are ready.
- Re-run the exact commit that will become `main` through the OpenBao and
  Windmill live paths, including a refreshed worker-local post-merge gate.
- Record the resulting structured receipt and then advance
  `versions/stack.yaml` to platform version `0.130.60`.
