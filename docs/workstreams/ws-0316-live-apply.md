# Workstream ws-0316-live-apply: Live Apply ADR 0316 From Latest `origin/main`

- ADR: [ADR 0316](../adr/0316-journey-analytics-and-onboarding-success-scorecards.md)
- Title: Live apply privacy-preserving journey analytics and onboarding success scorecards through the existing first-party operator admin surface
- Status: in-progress
- Branch: `codex/ws-0316-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0316-live-apply`
- Owner: codex
- Depends On: `adr-0242-guided-human-onboarding-via-shepherd-tours`,
  `adr-0281-glitchtip-as-the-sentry-compatible-application-error-tracker`,
  `adr-0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer`,
  `adr-0310-first-run-activation-checklists-and-progressive-capability-reveal`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0316`, `docs/workstreams/ws-0316-live-apply.md`,
  `docs/runbooks/configure-windmill.md`, `docs/runbooks/configure-plausible.md`,
  `docs/runbooks/windmill-operator-access-admin.md`,
  `inventory/host_vars/proxmox_florin.yml`,
  `collections/ansible_collections/lv3/platform/roles/windmill_runtime/**`,
  `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`,
  `config/windmill/scripts/**`, `scripts/journey_scorecards.py`, `tests/`,
  `receipts/live-applies/`, `workstreams.yaml`

## Scope

- add privacy-preserving journey milestone capture to the existing Windmill
  operator admin raw app without creating a second mutation path
- record durable onboarding and recovery milestones through repo-managed worker
  scripts so scorecards survive browser-local interruptions
- wire canonical route and milestone events into Plausible and user-visible
  journey failures into Glitchtip while keeping secrets and free-form content
  out of the emitted payloads
- surface scorecard output in repo automation and verify the live Windmill,
  Plausible, and evidence path end to end from the latest synchronized
  `origin/main` worktree

## Non-Goals

- replacing the broader ADR 0310 cross-surface activation-checklist work with a
  new platform shell in this change
- updating protected release files on this branch before a final mainline
  integration step
- expanding browser telemetry into content capture, secret capture, or general
  surveillance

## Expected Repo Surfaces

- `docs/adr/0316-journey-analytics-and-onboarding-success-scorecards.md`
- `docs/workstreams/ws-0316-live-apply.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/configure-plausible.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `inventory/host_vars/proxmox_florin.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/**`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`
- `config/windmill/scripts/**`
- `scripts/journey_scorecards.py`
- `tests/test_journey_scorecards.py`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-04-02-adr-0316-journey-analytics-live-apply.json`
- `receipts/live-applies/evidence/*ws-0316-*`
- `workstreams.yaml`

## Expected Live Surfaces

- the Windmill raw app `f/lv3/operator_access_admin` exposes onboarding
  scorecard progress and emits privacy-preserving journey milestones
- Plausible records canonical route and milestone analytics for the governed
  onboarding surface without capturing free-form content
- Glitchtip receives bounded failure signals for user-visible journey breaks
- the worker-side scorecard automation can render the current onboarding
  success report from live evidence

## Ownership Notes

- this workstream owns the branch-local ADR 0316 implementation, receipts, and
  verification evidence
- `docker-runtime-lv3`, Plausible, and Windmill remain shared live surfaces, so
  replay must stay rebased to the latest `origin/main` and avoid reverting
  unrelated runtime drift
- protected files remain deferred on this branch unless this thread becomes the
  final verified integration step on `main`

## Verification Plan

- targeted app and automation tests for the new journey contracts
- `./scripts/validate_repo.sh agent-standards`
- `make pre-push-gate`
- synchronized live converge for the affected service surfaces
- live verification of raw app source, scorecard output, Plausible event
  acceptance, and Glitchtip failure plumbing

## Merge-To-Main Notes

- still pending; protected release and canonical-truth files must wait for the
  final exact-main integration step
