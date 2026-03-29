# Workstream ws-0251-live-apply-r2: Stage-Scoped Smoke Suites And Promotion Gates

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Live apply stage-scoped smoke suites and promotion-gate enforcement from latest `origin/main`
- Status: live_applied
- Implemented In Repo Version: 0.177.84
- Live Applied In Platform Version: 0.130.59
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
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

## Current Progress

- 2026-03-29 focused validation passed from this worktree:
  `44 passed in 23.61s` across the stage-smoke, promotion-pipeline,
  service-catalog, runtime-assurance, and interactive ops-portal slices
- 2026-03-29 the live ops-portal replay exposed one packaging gap in the
  branch-local runtime role: `scripts/stage_smoke.py` was imported by the
  portal image but was not copied into the synced service tree or Docker build
  context; this branch now copies and packages the helper explicitly and adds
  image-layout regression coverage for that import path
- 2026-03-29 repo validation passed for
  `scripts/policy_checks.py --validate`,
  `scripts/promotion_pipeline.py --validate`,
  `make command-info COMMAND=promote-to-production`, and
  `make workflow-info WORKFLOW=deploy-and-promote`
- 2026-03-29 the guarded live promotion-gate replay proved the negative path
  from real staging data: `grafana` was rejected because the live catalog does
  not yet declare an active staging smoke suite and the staging receipt is
  stale
- 2026-03-29 the scoped `windmill` replay reached the live healthcheck,
  worker-registration, and seeded-script verification steps before failing in
  the Windmill `f/lv3/gate-status` verification path; transcript:
  `receipts/live-applies/evidence/2026-03-29-adr-0251-windmill-live-apply.txt`
  and drift diagnosis:
  `receipts/live-applies/evidence/2026-03-29-adr-0251-windmill-worker-drift.txt`
- 2026-03-29 the scoped `ops_portal` rerun proved the packaging fix by passing
  the container, listener, root-page, launcher, and runtime-assurance partial
  render checks before failing the final non-degraded assertion after the live
  API gateway on `docker-runtime-lv3` drifted back away from current
  `origin/main`; transcripts:
  `receipts/live-applies/evidence/2026-03-29-adr-0251-ops-portal-live-apply.txt`,
  `receipts/live-applies/evidence/2026-03-29-adr-0251-ops-portal-live-apply-rerun.txt`,
  recovery proof:
  `receipts/live-applies/evidence/2026-03-29-adr-0251-api-gateway-drift-recovery.txt`,
  and recurrence proof:
  `receipts/live-applies/evidence/2026-03-29-adr-0251-api-gateway-drift-recur.txt`
- 2026-03-29 the rebased exact-main `api_gateway` replay uncovered a second
  concurrency hazard on `docker-runtime-lv3`: tree-sync archives used fixed
  guest filenames like `/opt/api-gateway/collections-sync.tar.gz`, so parallel
  gateway replays could delete each other between copy and expand; this branch
  now derives a per-run guest archive filename inside
  `api_gateway_runtime/tasks/sync_tree.yml`, and
  `tests/test_api_gateway_runtime_role.py` covers that contract
- 2026-03-29 the first exact-main gateway replay and the immediate rerun prove
  two separate live issues clearly in branch-local evidence:
  `receipts/live-applies/evidence/2026-03-29-adr-0251-api-gateway-mainline-live-apply.txt`
  shows the fixed-name archive race, while
  `receipts/live-applies/evidence/2026-03-29-adr-0251-api-gateway-mainline-live-apply-rerun.txt`
  gets through the rebuild but still fails the final runtime-assurance route
  verification because another concurrent `api-gateway` replay clobbered the
  host back to the older `acc8…` implementation during verification
- 2026-03-29 this branch now carries one additional exact-main gateway fix:
  `api_gateway_runtime/defaults/main.yml` explicitly manages
  `config/environment-topology.json` alongside
  `config/runtime-assurance-matrix.json`, and
  `tests/test_api_gateway_runtime_role.py` covers that extra bundle member
- 2026-03-29
  `receipts/live-applies/evidence/2026-03-29-adr-0251-api-gateway-runtime-assurance-config-fix.txt`
  shows the first replay of that bundle fix; it gets through the config sync
  but loses the Docker build context again while another branch replays the
  same gateway host concurrently
- 2026-03-29
  `receipts/live-applies/evidence/2026-03-29-adr-0251-api-gateway-runtime-assurance-config-fix-rerun.txt`
  captures a clean-window rerun that completes successfully end to end,
  including the role's authenticated runtime-assurance verification, before a
  fresh concurrent `ws-0262-openfga-keycloak-live-apply` replay lands on the
  same host immediately afterward
- 2026-03-29
  `receipts/live-applies/evidence/2026-03-29-adr-0251-ops-portal-live-apply-postgateway.txt`
  plus direct post-apply inspection show the resulting live drift clearly: the
  portal partial falls back to the degraded banner again, the host keeps
  `environment-topology.json`, but `/opt/api-gateway/config/runtime-assurance-matrix.json`
  disappears from both the host bind mount and the running container after the
  later concurrent gateway replay
- 2026-03-29
  `receipts/live-applies/evidence/2026-03-29-adr-0251-api-gateway-postrebase-rerun.txt`
  completes successfully from the rebased exact-main worktree, and immediate
  post-run checks confirm `pve-manager/9.1.6`, a fresh public
  `https://api.lv3.org/v1/platform/runtime-assurance` envelope at
  `2026-03-29T17:12:50Z`, the updated ops-portal partial on `:8092`, and both
  `environment-topology.json` plus `runtime-assurance-matrix.json` present on
  the host bind mount and inside the running `api-gateway` container
- 2026-03-29
  `receipts/live-applies/evidence/2026-03-29-adr-0251-windmill-worker-checkout-rerun.txt`
  proves the branch-local `windmill` worker checkout refresh path still works:
  `/srv/proxmox_florin_server/scripts/stage_smoke.py` appears briefly, the live
  `promotion_pipeline.py` imports `stage_smoke`, and the updated
  `config/windmill/scripts/gate-status.py` wrapper lands on the host before a
  separate concurrent `ws-0266-main-integration-r2` replay overwrites the same
  shared checkout back to the older worker tree again; the narrow direct
  `ansible-playbook` replay itself later stops in the Windmill schedule-sync
  phase because that targeted recovery path bypasses the scoped runner's
  controller-side `PyYAML` dependency shell
- 2026-03-29
  `receipts/live-applies/evidence/2026-03-29-adr-0251-exact-main-durable-verification.txt`
  confirms the blocker is now resolved on current `origin/main`: the live
  worker checkout on `docker-runtime-lv3` keeps `scripts/stage_smoke.py`, both
  `promotion_pipeline.py` and `ops_portal/runtime_assurance.py` import it,
  `python3 config/windmill/scripts/gate-status.py --repo-path /srv/proxmox_florin_server`
  returns `status: ok`, the bounded exact-main promotion gate replay rejects
  the real staged `grafana` receipt because the receipt is stale, projected
  vCPU commitment `36.0` exceeds target `22.5`, and Prometheus SLO queries time
  out, the returned `stage_smoke_gate` payload stays `enforced=false` with
  `required_suite_ids=[]` and `observed_suites=[]`, and the authenticated
  runtime-assurance gateway plus local ops-portal runtime-assurance partial
  both verify cleanly on platform version `0.130.59`

## Live Apply Resolution

- the original shared-worker drift was cleared by the later exact-main Windmill
  convergence now present on current `origin/main`
- the current live worker checkout, gate-status wrapper, promotion gate, API
  gateway runtime-assurance route, and local ops-portal runtime-assurance panel
  all verify from the same exact-main platform state recorded in
  `2026-03-29-adr-0251-exact-main-durable-verification.txt`

## Remaining Steps

- none; ADR 0251 is fully live on the current verified platform baseline
  `0.130.59`
