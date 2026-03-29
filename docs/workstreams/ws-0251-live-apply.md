# Workstream WS-0251: Stage-Scoped Smoke Suites Live Apply

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Live apply stage-scoped smoke suites and promotion gates from the latest `origin/main`
- Status: merged
- Included In Repo Version: 0.177.82
- First Live Applied In Platform Version: 0.130.54
- Implemented On: 2026-03-29
- First Live Applied On: 2026-03-29
- Branch: `codex/ws-0251-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0251-live-apply`
- Owner: codex
- Depends On: `adr-0036-live-apply-receipts`, `adr-0044-windmill-for-background-automation`, `adr-0073-environment-promotion-gate-and-deployment-pipeline`, `adr-0087-repository-validation-gate`, `adr-0111-end-to-end-integration-test-suite`, `adr-0244-runtime-assurance-matrix-per-service-and-environment`
- Conflicts With: none

## Scope

- declare stage-scoped smoke suites per service and environment in a repo-managed catalog
- reuse the ADR 0111 integration suite as the execution engine for smoke proofs instead of inventing a parallel test harness
- require structured smoke-suite evidence in staged receipts before ADR 0073 promotions can pass
- expose the same smoke runner through Windmill and verify it live on the platform during this workstream
- record branch-local live-apply evidence so the final mainline merge can safely update canonical truth

## Non-Goals

- replacing probes, synthetic transaction replay, or restore verification with smoke suites
- publishing long-lived staging surfaces for services that are still only planned in staging
- rewriting protected integration files on this workstream branch before the final verified merge-to-main step

## Expected Repo Surfaces

- `config/stage-smoke-suites.json`
- `docs/schema/stage-smoke-suites.schema.json`
- `scripts/stage_smoke_suites.py`
- `scripts/integration_suite.py`
- `scripts/promotion_pipeline.py`
- `scripts/live_apply_receipts.py`
- `scripts/script_bootstrap.py`
- `scripts/windmill_run_wait_result.py`
- `config/service-capability-catalog.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`
- `playbooks/windmill.yml`
- `config/windmill/scripts/stage-smoke-suites.py`
- `config/windmill/scripts/windmill_integration_env.py`
- `platform/datetime_compat.py`
- `platform/enum_compat.py`
- `platform/ansible/__init__.py`
- `platform/scheduler/windmill_client.py`
- `docs/runbooks/environment-promotion-pipeline.md`
- `docs/runbooks/integration-test-suite.md`
- `docs/runbooks/live-apply-receipts-and-verification-evidence.md`
- `docs/runbooks/configure-windmill.md`
- `tests/test_windmill_integration_wrappers.py`
- `tests/test_windmill_operator_admin_app.py`
- `tests/test_windmill_playbook.py`
- `tests/test_script_bootstrap.py`

## Expected Live Surfaces

- Windmill carries a seeded repo-managed smoke-suite wrapper alongside the existing healthcheck and gate-status helpers
- the production Windmill runtime can execute the declared `windmill` smoke suite against the live platform checkout
- staged promotion receipts can carry structured smoke-suite evidence that the promotion pipeline understands and enforces

## Verification Plan

- focused unit tests for the new smoke-suite catalog, receipt validation, promotion gating, and integration-suite targeting
- repository validation and gate automation from the latest branch state
- `make converge-windmill` plus live Windmill job execution of the seeded smoke-suite wrapper
- committed live-apply receipt and evidence files for the verified production smoke run

## Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_windmill_integration_wrappers.py tests/test_integration_suite.py tests/test_stage_smoke_suites.py tests/test_windmill_playbook.py tests/test_windmill_default_operations_surface.py tests/test_backup_coverage_ledger.py tests/test_backup_coverage_ledger_windmill.py tests/test_disaster_recovery.py` returned `24 passed` after the latest worker-local wrapper and checkout-sync fixes.
- `uv run --with pytest pytest -q tests/test_windmill_operator_admin_app.py tests/test_windmill_playbook.py tests/test_windmill_default_operations_surface.py` returned `18 passed` after the hidden `.gitea` worker sync fix.
- `uv run --with pytest pytest -q tests/test_docker_runtime_role.py tests/test_windmill_operator_admin_app.py tests/test_proxmox_tailscale_proxy_role.py` returned `24 passed` after rebasing the branch onto the latest `origin/main` and preserving the Windmill wait-budget, Docker NAT-chain, OpenBao retry, and Tailscale proxy idempotency fixes.
- `./scripts/validate_repo.sh agent-standards` and `ANSIBLE_HOME=$PWD/.ansible-home-apply ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check` both passed from this isolated worktree after the final rebase.
- `make converge-windmill` succeeded twice from the earlier latest-`origin/main` branch head, with committed evidence in `receipts/live-applies/evidence/2026-03-29-adr-0251-converge-windmill-rerun-12.txt` and `receipts/live-applies/evidence/2026-03-29-adr-0251-converge-windmill-rerun-13.txt`.
- Controller-side `scripts/windmill_run_wait_result.py` successfully ran `f/lv3/stage-smoke-suites` against the live platform and the returned payload resolved `windmill_url` to the worker-local `http://127.0.0.1:8000` path.
- Worker-side `python3 scripts/policy_checks.py --validate`, `python3 scripts/command_catalog.py --check-approval --command converge-windmill --requester-class human_operator --approver-classes human_operator --validation-passed --preflight-passed --receipt-planned`, and `python3 config/windmill/scripts/gate-status.py --repo-path /srv/proxmox_florin_server` all passed after the worker checkout began mirroring `.gitea/workflows`.
- A direct helper replay of `f/lv3/windmill_healthcheck` returned `status: ok` with `hostname: docker-runtime-lv3`, proving the current live Windmill runtime is still healthy after the ADR 0251 replay.
- The latest rebased replay attempts are preserved in `receipts/live-applies/evidence/2026-03-29-adr-0251-converge-windmill-mainline-rerun-14.txt` through `...-17.txt`; they show that the branch-local replay progressed through the new wait-budget and Docker fixes but the final stage-smoke assertion stayed unstable because concurrent main-based worker-checkout refreshes kept removing ADR 0251 files from `/srv/proxmox_florin_server` before `origin/main` carried them.

## Live Apply Outcome

- ADR 0251 is live on production through the repo-managed stage smoke suite catalog, promotion-gate receipt enforcement, and the seeded Windmill `f/lv3/stage-smoke-suites` wrapper.
- The live apply also hardened the worker runtime around current Python packaging drift by adding compatibility helpers, worker-local Windmill env discovery, and hidden workflow checkout sync for worker-side approval validation.
- The canonical branch-local evidence is recorded in `receipts/live-applies/2026-03-29-adr-0251-stage-smoke-suites-live-apply.json`.

## Mainline Integration Outcome

- Release `0.177.82` is the first repository version that records ADR 0251 implemented on `main`.
- Platform version `0.130.54` remains the first observed platform version where ADR 0251 became true during the branch-local live apply.
- The canonical receipt pointers, `README.md` integrated status summary, and `versions/stack.yaml` live-apply surfaces intentionally wait for the post-merge exact-main replay because stable verification depends on `origin/main` containing the ADR 0251 worker-checkout files.

## Merge-To-Main Notes

- remaining after the first merge commit: push `0.177.82` to `origin/main`, replay `make converge-windmill` from the main-equivalent checkout, verify `f/lv3/stage-smoke-suites` returns a passing structured result without the worker-checkout churn, then update `README.md`, `versions/stack.yaml`, the workstream status, and the canonical receipt pointers in a final exact-main follow-up commit
