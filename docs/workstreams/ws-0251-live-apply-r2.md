# Workstream ws-0251-live-apply-r2: Stage-Scoped Smoke Suites And Promotion Gates

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Live apply stage-scoped smoke suites and promotion-gate enforcement from latest `origin/main`
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0251-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0251-live-apply-r2`
- Owner: codex
- Depends On: `adr-0073-promotion-gate`, `adr-0111-integration-test-suite`,
  `adr-0244-runtime-assurance-matrix`, `adr-0253-runtime-assurance-scoreboard`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0251-live-apply-r2.md`,
  `docs/adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md`,
  `docs/adr/.index.yaml`, `docs/schema/service-capability-catalog.schema.json`,
  `scripts/stage_smoke.py`, `scripts/service_catalog.py`,
  `scripts/promotion_pipeline.py`, `scripts/ops_portal/runtime_assurance.py`,
  `policy/decisions/release_promotion.rego`,
  `policy/tests/release_promotion_test.rego`,
  `docs/runbooks/environment-promotion-pipeline.md`,
  `docs/runbooks/runtime-assurance-scoreboard.md`,
  `docs/runbooks/service-capability-catalog.md`,
  `tests/test_stage_smoke.py`, `tests/test_promotion_pipeline.py`,
  `tests/test_runtime_assurance_scoreboard.py`,
  `tests/test_validate_service_catalog.py`, `receipts/live-applies/`

## Scope

- add one governed stage-smoke contract that both the promotion gate and the
  runtime-assurance scoreboard consume
- keep active environments covered by a repo-managed default smoke suite unless
  a service declares an explicit override in the service catalog
- enforce the ADR 0251 smoke requirement in the promotion policy so stale or
  non-smoke staging receipts become first-class blockers
- live-apply the affected operator/runtime surfaces and record branch-local
  evidence plus merge-to-main requirements clearly

## Expected Repo Surfaces

- `docs/adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md`
- `docs/workstreams/ws-0251-live-apply-r2.md`
- `workstreams.yaml`
- `docs/adr/.index.yaml`
- `docs/schema/service-capability-catalog.schema.json`
- `scripts/stage_smoke.py`
- `scripts/service_catalog.py`
- `scripts/promotion_pipeline.py`
- `scripts/ops_portal/runtime_assurance.py`
- `policy/decisions/release_promotion.rego`
- `policy/tests/release_promotion_test.rego`
- `docs/runbooks/environment-promotion-pipeline.md`
- `docs/runbooks/runtime-assurance-scoreboard.md`
- `docs/runbooks/service-capability-catalog.md`
- `tests/test_stage_smoke.py`
- `tests/test_promotion_pipeline.py`
- `tests/test_validate_service_catalog.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- the live ops portal scoreboard uses declared or inherited stage smoke suites
  instead of treating any recent receipt as smoke proof
- the live Windmill-backed promotion workflow rejects staged receipts that do
  not satisfy the declared smoke suite contract
- one fresh live receipt proves at least one production service through the new
  smoke-suite matching path

## Verification Plan

- run the focused policy, smoke, promotion, service-catalog, and runtime
  assurance test slice plus the standard repo validation gates
- replay the live ops-portal and Windmill surfaces from this isolated
  latest-`origin/main` worktree
- verify the live ops portal section renders with the updated smoke behaviour
  and verify the live promotion gate rejects a non-smoke staging receipt with a
  concrete ADR 0251 reason

## Notes For The Next Assistant

- keep `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml` off
  this workstream branch until the final integration step on `main`
- if a live staging service is still not declared active in the service
  catalog, the promotion-gate live proof should stay a guarded rejection rather
  than inventing unsupported stage-ready truth
