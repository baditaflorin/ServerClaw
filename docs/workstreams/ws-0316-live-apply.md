# Workstream ws-0316-live-apply: Live Apply ADR 0316 From Latest `origin/main`

- ADR: [ADR 0316](../adr/0316-journey-analytics-and-onboarding-success-scorecards.md)
- Title: Live apply privacy-preserving journey analytics and onboarding success scorecards through the existing first-party operator admin surface
- Status: merged
- Included In Repo Version: 0.177.141
- Branch-Local Receipt: `receipts/live-applies/2026-04-02-adr-0316-journey-analytics-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0316-journey-analytics-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.89
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.140`, platform `0.130.88`
- Branch: `codex/ws-0316-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0316-live-apply`
- Owner: codex
- Depends On: `adr-0242-guided-human-onboarding-via-shepherd-tours`, `adr-0281-glitchtip-as-the-sentry-compatible-application-error-tracker`, `adr-0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer`, `adr-0310-first-run-activation-checklists-and-progressive-capability-reveal`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0316-live-apply.md`, `docs/adr/0316-journey-analytics-and-onboarding-success-scorecards.md`, `docs/adr/.index.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/runbooks/configure-windmill.md`, `docs/runbooks/configure-plausible.md`, `docs/runbooks/windmill-operator-access-admin.md`, `inventory/host_vars/proxmox_florin.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/**`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `config/windmill/scripts/**`, `scripts/journey_scorecards.py`, `tests/test_journey_scorecards.py`, `tests/test_windmill_operator_admin_app.py`, `docs/site-generated/architecture/dependency-graph.md`, `receipts/ops-portal-snapshot.html`, `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`, `receipts/live-applies/2026-04-02-adr-0316-journey-analytics-live-apply.json`, `receipts/live-applies/2026-04-02-adr-0316-journey-analytics-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0316-*`

## Scope

- add privacy-preserving journey milestone capture to the existing Windmill
  operator admin raw app without creating a second mutation path
- record durable onboarding and recovery milestones through repo-managed worker
  scripts so scorecards survive browser-local interruptions
- wire canonical route and milestone events into Plausible and bounded
  user-visible failure events into Glitchtip while keeping secrets and
  free-form content out of the emitted payloads
- surface scorecard output in repo automation and verify the live Windmill,
  Plausible, and evidence path end to end from the latest synchronized
  `origin/main` worktree

## Non-Goals

- replacing the broader ADR 0310 cross-surface activation-checklist work with a
  new platform shell in this change
- reworking the shared ADR 0281 Glitchtip publication/runtime implementation
  beyond the narrow integration points that ADR 0316 depends on
- hiding shared runtime gaps behind a false-green live-apply receipt

## Expected Repo Surfaces

- `docs/adr/0316-journey-analytics-and-onboarding-success-scorecards.md`
- `docs/workstreams/ws-0316-live-apply.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/configure-plausible.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `scripts/journey_scorecards.py`
- `tests/test_journey_scorecards.py`
- `tests/test_windmill_operator_admin_app.py`
- `versions/stack.yaml`
- `workstreams.yaml`
- `receipts/live-applies/2026-04-02-adr-0316-journey-analytics-live-apply.json`
- `receipts/live-applies/2026-04-02-adr-0316-journey-analytics-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-04-02-ws-0316-*`

## Expected Live Surfaces

- the Windmill raw app `f/lv3/operator_access_admin` exposes onboarding
  scorecard progress and emits privacy-preserving journey milestones
- the worker-side automation keeps durable journey state under
  `.local/state/journey-analytics/` and renders the current latest report
- Plausible records canonical route analytics for the governed onboarding
  surface without capturing free-form content
- Glitchtip delivery stays bounded and fail-closed; until ADR 0281 is fully
  live on `errors.lv3.org`, the report keeps `glitchtip_events` at `0`

## Ownership Notes

- this workstream owns the branch-local ADR 0316 implementation, receipts, and
  verification evidence
- `docker-runtime-lv3`, Plausible, Windmill, and the release/canonical-truth
  files are shared surfaces, so the exact-main replay stayed rebased to the
  latest `origin/main` and avoided reverting unrelated drift
- the exact-main replay promoted the protected release and platform-truth
  surfaces on `codex/ws-0316-main-integration`
- the remaining Glitchtip publication/runtime gap is recorded explicitly as a
  shared ADR 0281 blocker rather than being hidden inside the ADR 0316 receipt

## Branch-Local Verification

- `receipts/live-applies/evidence/2026-04-02-ws-0316-mainline-release-status-r2.json`
  and `...release-manager-r4.txt` show the exact-main replay cut repository
  version `0.177.141` from the latest realistic `origin/main` baseline
  `0.177.140`.
- `receipts/live-applies/evidence/2026-04-02-ws-0316-mainline-converge-plausible-r3.txt`
  and `...converge-windmill-r4.txt` capture the governed live replays that
  synchronized Plausible, the Windmill worker checkout, the raw app, the
  helper scripts, and the refreshed host SBOM receipt from the exact worktree.
- `receipts/live-applies/evidence/2026-04-02-ws-0316-mainline-journey-schedule-r2.json`,
  `...journey-event-smoke-r4.json`, `...journey-scorecards-r5.json`, and
  `...worker-state-r2.json` confirm the daily `f/lv3/operator_journey_scorecards`
  schedule is enabled for `08:15` `Europe/Bucharest`, the live helper accepted
  the full milestone stream, and the worker ledger/latest report now contain
  `52` durable events across `3` sessions and `3` visitors with all six
  scorecards `ok`.
- `receipts/live-applies/evidence/2026-04-02-ws-0316-mainline-plausible-route-smoke-r2.json`
  and `...journey-scorecards-r5.json` show the exact-main route smoke advanced
  all nine governed `/journeys/operator-access-admin/*` pageview counters by
  `+1`, leaving the live report at `2` pageviews per governed route.
- `receipts/live-applies/evidence/2026-04-02-ws-0316-mainline-glitchtip-publication-r2.json`
  and `...glitchtip-runtime-state-r3.json` preserve the remaining shared
  blocker: the helper's DSN normalization is fixed, but `errors.lv3.org` still
  fails TLS hostname validation, resolves to the shared public edge at
  `65.108.75.123`, and the `glitchtip_default` Docker network has no attached
  service containers on `docker-runtime-lv3`.

## Exact-Main Validation

- after updating ADR/workstream metadata, receipts, and platform truth, the
  exact-main tree reran the generated-truth scripts plus the local, remote, and
  pre-push validation bundles before the merge to `main`
- the canonical mainline receipt records the final successful validation suite,
  including `scripts/validate_repository_data_models.py --validate`,
  `scripts/live_apply_receipts.py --validate`,
  `./scripts/validate_repo.sh agent-standards`,
  `./scripts/validate_repo.sh workstream-surfaces`, `make validate`,
  `make remote-validate`, `make pre-push-gate`, and `git diff --check`

## Remaining Shared Follow-Up

- ADR 0316 is live for browser milestones, durable worker scorecards, and
  Plausible route analytics
- the remaining platform gap is ADR 0281 publication/runtime repair for
  `errors.lv3.org`; once that shared surface is live, rerun
  `f/lv3/operator_journey_scorecards` and confirm `glitchtip_events` rises
  above `0`
