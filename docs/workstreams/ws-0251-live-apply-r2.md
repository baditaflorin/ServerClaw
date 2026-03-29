# Workstream ws-0251-live-apply-r2: Stage-Scoped Smoke Suites And Promotion Gates

- ADR: [ADR 0251](../adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md)
- Title: Live apply stage-scoped smoke suites and promotion-gate enforcement from latest `origin/main`
- Status: merged
- Implemented In Repo Version: 0.177.84
- Live Applied In Platform Version: N/A
- Implemented On: 2026-03-29
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
- the latest clean-window rerun confirms the newer config-bundle fix is real
  but still not stable against concurrent older replays: this worktree's green
  `2026-03-29-adr-0251-api-gateway-runtime-assurance-config-fix-rerun` replay
  verifies the authenticated runtime-assurance route during the play itself,
  then a fresh `ws-0262-openfga-keycloak-live-apply` gateway replay starts
  again and leaves the shared host with `environment-topology.json` present
  but `runtime-assurance-matrix.json` missing, which immediately restores the
  ops-portal degraded fallback banner and a live `500` from
  `/v1/platform/runtime-assurance`
- the latest targeted Windmill worker-checkout rerun confirms the repo changes
  themselves are correct but the shared runtime host is still not stable enough
  to claim ADR 0251 fully live: this worktree briefly restores
  `scripts/stage_smoke.py`, the `stage_smoke` import in
  `/srv/proxmox_florin_server/scripts/promotion_pipeline.py`, and the updated
  `gate-status` wrapper, but an overlapping
  `ws-0266-main-integration-r2` `windmill.yml` replay on the same
  `docker-runtime-lv3` guest removes `scripts/stage_smoke.py` and reverts the
  worker checkout before a durable negative-path promotion proof can be
  recorded

## Remaining Steps

- replay `windmill` from an uncontended exact-main checkout after the current
  concurrent `windmill.yml` writers stop clobbering `/srv/proxmox_florin_server`
  on `docker-runtime-lv3`
- only after that clean-window replay holds through verification: mark
  ADR 0251 fully implemented, set `workstreams.yaml` `live_applied: true`, and
  update `versions/stack.yaml` live evidence plus the integrated README live
  status to the verified platform truth
