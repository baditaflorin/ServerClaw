# Workstream WS-0251: Stage-Scoped Smoke Suites Live Apply

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Live apply stage-scoped smoke suites and promotion gates from the latest `origin/main`
- Status: in_progress
- Implemented In Repo Version: pending
- Live Applied In Platform Version: pending
- Implemented On: pending
- Live Applied On: pending
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
- `config/service-capability-catalog.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`
- `config/windmill/scripts/stage-smoke-suites.py`
- `docs/runbooks/environment-promotion-pipeline.md`
- `docs/runbooks/integration-test-suite.md`
- `docs/runbooks/live-apply-receipts-and-verification-evidence.md`
- `docs/runbooks/configure-windmill.md`

## Expected Live Surfaces

- Windmill carries a seeded repo-managed smoke-suite wrapper alongside the existing healthcheck and gate-status helpers
- the production Windmill runtime can execute the declared `windmill` smoke suite against the live platform checkout
- staged promotion receipts can carry structured smoke-suite evidence that the promotion pipeline understands and enforces

## Verification Plan

- focused unit tests for the new smoke-suite catalog, receipt validation, promotion gating, and integration-suite targeting
- repository validation and gate automation from the latest branch state
- `make converge-windmill` plus live Windmill job execution of the seeded smoke-suite wrapper
- committed live-apply receipt and evidence files for the verified production smoke run

## Merge-To-Main Notes

- protected integration files will wait until the final verified merge-to-main step
