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

## Live Apply Blocker

- the shared worker checkout on `docker-runtime-lv3` did not remain on this
  worktree snapshot through verification
- after the replay, `/srv/proxmox_florin_server/scripts/promotion_pipeline.py`
  and `/srv/proxmox_florin_server/scripts/ops_portal/runtime_assurance.py`
  matched `origin/main`, `scripts/stage_smoke.py` was missing, and
  `scripts/gate_status.py` had drifted to a newer branch-local variant that
  imports `gate_bypass_waivers`
- direct reproduction on `docker-runtime-lv3`:
  `python3 config/windmill/scripts/gate-status.py --repo-path /srv/proxmox_florin_server`
  failed with `ModuleNotFoundError: No module named 'gate_bypass_waivers'`
- this is consistent with concurrent branch-local replays clobbering the
  shared Windmill worker checkout on `docker-runtime-lv3`; the role expanded a
  staged archive during this run, but the verified guest hashes no longer
  matched the ADR 0251 worktree by the time the Windmill gate-status script ran
- the live API gateway on `docker-runtime-lv3` is also subject to the same
  shared-host drift: it was first recovered to the current repo and current
  `origin/main` hash `ce9f9ff50a64f2edbad20eced497f25efa5d5baffc2d181169c7025841b35853`,
  then later reverted to
  `acc8a2750d95323ca8337265064e082d1f0ae0e8c6fc63ca4a2b3dae116242f7`,
  which removes `/v1/platform/runtime-assurance` from the live gateway and
  forces the ops portal back onto the degraded fallback banner during final
  verification
- the exact-main gateway rerun confirms the overwrite is coming from another
  branch-local replay, not from this worktree: while this branch expected
  `ce9f…`, the live host and container stayed on `acc8…`, and local controller
  process inspection showed a concurrent `ws-0257-main-merge` `playbooks/api-gateway.yml`
  replay targeting the same host during the same verification window

## Remaining Steps

- fetch and rebase onto the latest `origin/main` before any final integration:
  during this run the worktree moved again and `origin/main` is now
  `7f1bbe50518fd30a78a2ce5f7ee5f410ba07b0ea` as of 2026-03-29
- re-run `api-gateway`, then the exact `ops_portal` and `windmill` live applies
  from an uncontended latest-main checkout and verify the guest hashes
  immediately after each replay so the shared host cannot drift between apply
  and proof
- update ADR 0251 metadata, refresh `docs/adr/.index.yaml`, and mark
  `workstreams.yaml` `live_applied: true` only after the live hashes and public
  behavior match the final merged tree
- only in the final merge-to-main step: bump `VERSION`, update
  `changelog.md`, refresh integrated `README.md` status, and set
  `versions/stack.yaml` to the verified live platform truth
