# Workstream ws-0251-main-integration-r2

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Integrate ADR 0251 latest-server-state follow-up onto `origin/main`
- Status: `merged`
- Target Repo Version: 0.177.101
- Target Platform Version: 0.130.68
- Release Date: 2026-03-30
- Branch: `codex/ws-0251-main-integration-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0251-live-apply`
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

## Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_windmill_operator_admin_app.py` returned `14 passed in 0.24s` after pinning `make converge-windmill` to the active worktree checkout.
- Release `0.177.101` was cut on the merged branch, producing committed source `57b077a1c4477d179731db3a7148a74f9cf9070a`.
- `make converge-docker-runtime env=production`, `make converge-step-ca env=production`, `make converge-openbao env=production`, and `make converge-windmill env=production` all succeeded from that committed source, with evidence in `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r43-converge-docker-runtime-0.177.101.txt` through `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r46-converge-windmill-0.177.101.txt`.
- Worker-side `make post-merge-gate` completed from `/srv/proxmox-host_server`, the live `f/lv3/gate-status` wrapper returned `status: ok` with `post_merge_run.status: passed` and `requested_checks: ["local-fallback"]`, and `f/lv3/stage-smoke-suites` passed `production-windmill-primary-path`, with evidence in `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r47-post-merge-gate-0.177.101.txt` through `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r49-stage-smoke-suites-0.177.101.json`.
- The authenticated runtime-assurance API returned summary `55 total / 36 pass / 19 degraded / 0 failed / 0 unknown`, fresh host and guest probes reconfirmed `pve-manager/9.1.6`, kernel `6.17.13-2-pve`, Windmill `CE v1.662.0`, and healthy unsealed OpenBao `2.5.1`, and worker checkout hashes matched the active worktree across the six pinning-sensitive files, with evidence in `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r50-runtime-assurance-0.177.101.json` through `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r54-worker-checkout-parity-0.177.101.txt`.
- The governed promotion gate still rejected the stale staged Grafana receipt for the expected reasons: Prometheus SLO query timeouts, projected vCPU commitment `36.0` above target `22.5`, and receipt age, while `approval.approved`, `stage_smoke_gate.passed`, and `staging_health_check.passed` remained true.

## Outcome

- Release `0.177.101` records this follow-up on `main`.
- Platform version `0.130.68` is the verified mainline baseline after the newest exact-main replay.
- The canonical receipt is `receipts/live-applies/2026-03-30-adr-0251-stage-smoke-promotion-gates-mainline-live-apply.json`.
