# Workstream WS-0251: Stage-Scoped Smoke Suites Live Apply

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Live apply stage-scoped smoke suites and promotion gates from the latest `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.86
- First Live Applied In Platform Version: 0.130.58
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
- `uv run --with pytest --with pyyaml pytest -q tests/test_openbao_runtime_role.py tests/test_openbao_compose_env_helper.py tests/test_validation_gate.py tests/test_validation_gate_windmill.py tests/test_stage_smoke_suites.py tests/test_windmill_integration_wrappers.py tests/test_changelog_portal.py tests/test_changelog_redaction.py` returned `34 passed` after hardening `scripts/deployment_history.py` to ignore nested evidence JSON that is not a live-apply receipt and after teaching `openbao_runtime` to continue through transient post-restart Docker chain loss until runtime checks can make the final decision.
- `./scripts/validate_repo.sh generated-vars role-argument-specs json alert-rules generated-docs generated-portals agent-standards`, `uv run --with pyyaml python3 scripts/canonical_truth.py --check`, and `ANSIBLE_HOME=$PWD/.ansible-home-apply ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check` all passed from this isolated worktree after the portal regression fix.
- `make converge-windmill` succeeded from the latest branch head with evidence in `receipts/live-applies/evidence/2026-03-29-adr-0251-converge-windmill-post-portal-fix.txt`; the recap reported `docker-runtime-lv3 : ok=257 changed=49 failed=0`, `postgres-lv3 : ok=64 changed=0 failed=0`, and `proxmox_florin : ok=42 changed=7 failed=0`.
- Worker-side `make post-merge-gate` succeeded on `/srv/proxmox_florin_server` with evidence in `receipts/live-applies/evidence/2026-03-29-adr-0251-post-merge-gate-live-worker.txt`, and refreshed `.local/validation-gate/post-merge-last-run.json` so the guest-local `post_merge_run` surface returned to `passed`.
- Direct live replays of `config/windmill/scripts/gate-status.py`, `f/lv3/stage-smoke-suites`, and `f/lv3/windmill_healthcheck` all passed after the worker-side post-merge gate, with evidence in `receipts/live-applies/evidence/2026-03-29-adr-0251-gate-status-live-post-merge-gate.json`, `receipts/live-applies/evidence/2026-03-29-adr-0251-stage-smoke-suites-live-post-merge-gate.json`, and `receipts/live-applies/evidence/2026-03-29-adr-0251-windmill-healthcheck-live-post-merge-gate.json`.
- A latest-server-state inspection on `docker-runtime-lv3` found OpenBao drifted down even while Windmill remained healthy; `make converge-openbao` first exposed a real recovery gap around post-restart `DOCKER` and `DOCKER-FORWARD` chain rechecks, then succeeded after the role hardening, with the successful rerun captured in `receipts/live-applies/evidence/2026-03-29-openbao-recovery-after-server-state-check-rerun.txt`.
- Post-recovery OpenBao verification succeeded with evidence in `receipts/live-applies/evidence/2026-03-29-openbao-docker-compose-ps-post-recovery.txt` and `receipts/live-applies/evidence/2026-03-29-openbao-health-and-approle-post-recovery.json`, confirming `lv3-openbao` rebounded on `0.0.0.0:8200` and `127.0.0.1:8201`, reported `status: 200`, `initialized: true`, `sealed: false`, `standby: false`, `version: 2.5.1`, and accepted repeated AppRole logins from the repo-managed shared artifacts.
- `make converge-windmill` also succeeded again after the OpenBao recovery, with evidence in `receipts/live-applies/evidence/2026-03-29-adr-0251-converge-windmill-after-openbao-recovery.txt`, confirming the follow-up guest repair did not regress the live Windmill convergence path.
- Fresh host and guest snapshots in `receipts/live-applies/evidence/2026-03-29-adr-0251-latest-server-state-pre-merge-host.txt` and `receipts/live-applies/evidence/2026-03-29-adr-0251-latest-server-state-pre-merge-guest.txt` confirmed the current live baseline immediately before merge preparation: `pve-manager/9.1.6`, kernel `6.17.13-2-pve`, Windmill `CE v1.662.0`, OpenBao `2.5.1` healthy and unsealed, the `lv3-openbao` compose service running on both published ports, and the worker-local `post_merge_run` still `passed`.
- The later exact-main replay from committed source `57b077a1c4477d179731db3a7148a74f9cf9070a` re-cut release `0.177.101`, reran `make converge-docker-runtime`, `make converge-step-ca`, `make converge-openbao`, and `make converge-windmill` with green recaps in `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r43-converge-docker-runtime-0.177.101.txt` through `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r46-converge-windmill-0.177.101.txt`, confirmed worker hash parity and a passed worker-local post-merge gate in `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r47-post-merge-gate-0.177.101.txt` and `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r54-worker-checkout-parity-0.177.101.txt`, passed the live `f/lv3/gate-status` and `f/lv3/stage-smoke-suites` wrappers in `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r48-gate-status-0.177.101.json` and `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r49-stage-smoke-suites-0.177.101.json`, refreshed runtime-assurance plus host and guest state in `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r50-runtime-assurance-0.177.101.json` through `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r53-docker-runtime-state-0.177.101.txt`, and reconfirmed the governed promotion gate still rejects the stale staged Grafana receipt in `receipts/live-applies/evidence/2026-03-30-adr-0251-mainline-r51-promotion-gate-0.177.101.txt`.

## Live Apply Outcome

- ADR 0251 is live on production through the repo-managed stage smoke suite catalog, promotion-gate receipt enforcement, and the seeded Windmill `f/lv3/stage-smoke-suites` wrapper.
- The live apply also hardened the worker runtime around current Python packaging drift by adding compatibility helpers, worker-local Windmill env discovery, and hidden workflow checkout sync for worker-side approval validation.
- Follow-up branch-local verification also fixed the deployment-history portal so nested evidence JSON no longer breaks changelog rendering, and it hardened OpenBao recovery so latest-server-state checks can repair the current Docker chain drift without resorting to undocumented manual guest changes.
- The canonical branch-local evidence is recorded in `receipts/live-applies/2026-03-29-adr-0251-stage-smoke-suites-live-apply.json`.

## Mainline Integration Outcome

- Release `0.177.86` is the first repository version that records ADR 0251 implemented on `main`.
- Platform version `0.130.58` remains the first verified platform version where ADR 0251 became true during the branch-local live apply.
- Release `0.177.87` carries the exact-main durable verification that confirms the live worker checkout keeps the stage-smoke helper durable, the worker-local gate-status replay stays healthy, and the live API-gateway plus ops-portal surfaces stay aligned on the current verified platform baseline `0.130.59`.
- Release `0.177.101` carries the later exact-main replay after `origin/main` advanced again on `2026-03-30`: the active worktree now pins the Windmill worker mirror during converge, the worker-local `post_merge_run` remains `passed`, the live smoke wrapper still passes `production-windmill-primary-path`, and the canonical receipt now advances the verified mainline platform baseline to `0.130.68`.
- The canonical exact-main receipt is `receipts/live-applies/2026-03-30-adr-0251-stage-smoke-promotion-gates-mainline-live-apply.json`; it supersedes the older `2026-03-29` canonical receipt for the current `promotion_pipeline`, `stage_smoke_suites`, and OpenBao follow-up evidence pointers, while the earlier branch-local receipt remains preserved as the first successful isolated-worktree live apply.

## Merge-To-Main Notes

- Merge-to-main is complete in release `0.177.101`: the exact-main replay, canonical receipt, and protected truth surfaces now agree on the verified `0.130.68` production baseline.
