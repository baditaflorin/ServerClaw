# Workstream ws-0308-journey-live-apply: Live Apply ADR 0308 Journey Routing From Latest `origin/main`

- ADR: [ADR 0308](../adr/0308-journey-aware-entry-routing-and-saved-home-selection.md)
- Title: Ship the journey-aware entry router, saved-home selection, activation-first start surface, and the integrated attention-first portal shell on the interactive ops portal
- Status: live_applied
- Included In Repo Version: `0.177.144`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`
- Live Applied In Platform Version: `0.130.91`
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.143`, platform `0.130.90`
- Branch: `codex/ws-0308-live-apply-r3`
- Worktree: `.worktrees/ws-0308-live-apply-r2`
- Owner: codex
- Depends On: `adr-0093`, `adr-0152`, `adr-0235`, `adr-0242`, `adr-0310`, `adr-0312`, `adr-0313`
- Conflicts With: `ws-0308-live-apply`
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0308-journey-live-apply.md`, `docs/workstreams/adr-0307-platform-app-cohesion-bundle.md`, `docs/adr/0308-journey-aware-entry-routing-and-saved-home-selection.md`, `docs/adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md`, `docs/adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md`, `docs/adr/.index.yaml`, `docs/runbooks/platform-operations-portal.md`, `scripts/ops_portal/app.py`, `scripts/ops_portal/templates/base.html`, `scripts/ops_portal/templates/entry.html`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/templates/partials/activation.html`, `scripts/ops_portal/templates/partials/attention.html`, `scripts/ops_portal/templates/partials/launcher.html`, `scripts/ops_portal/static/portal.css`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_playbook.py`, `tests/test_ops_portal_runtime_role.py`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-*`, `receipts/restic-backups/20260402T131708Z.json`, `receipts/restic-snapshots-latest.json`, `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`

## Purpose

Implement the journey-aware `/entry` router on top of the latest realistic
`origin/main` portal runtime and carry the merged ADR 0310 and ADR 0312 portal
surfaces through the same exact-main replay so authenticated users land on the
right start surface, complete first-run activation safely, and see shared
attention signals without losing the saved-home and deep-link guarantees.

## Scope

- add a neutral `/entry` route and durable saved-home selection to the
  interactive ops portal
- keep first-run users on the activation-aware surface until they complete or
  skip onboarding gates
- surface the shared notification center and activity timeline inside the same
  first-party portal shell
- harden the managed runtime replay so the shared search-fabric sync survives
  transient runtime-tree churn during live apply
- document and preserve the exact-main live-apply evidence, release-truth
  update, backup receipt, and refreshed SBOM

## Outcome

- The final exact-main integration promoted the combined portal change to
  repository version `0.177.144` and platform version `0.130.91` from the
  latest realistic baseline `0.177.143 / 0.130.90`.
- The exact-main replay succeeded with
  `docker-runtime-lv3 : ok=194 changed=16 unreachable=0 failed=0 skipped=40 rescued=0 ignored=0`
  after adding a bounded retry around the shared search-fabric copy step in the
  managed `ops_portal_runtime` role.
- The integrated runtime now serves the journey-aware neutral start surface, the
  first-run activation checklist, the shared notification center, and the
  launcher/search shell from the same governed production deployment.
- The replay refreshed the governed restic config-backup receipt
  `receipts/restic-backups/20260402T131708Z.json`, updated
  `receipts/restic-snapshots-latest.json`, and regenerated the host SBOM at
  `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`.

## Verification

- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-syntax-check-r3.txt`
  and `...targeted-tests-r3.txt` capture the focused portal regression slice,
  including `47 passed` across the interactive portal runtime, playbook, and
  runtime-role tests.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-live-apply-r6-combined.txt`
  captures the final governed production replay from the exact worktree with
  the runtime-role correction applied.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-ops-portal-guest-runtime-r4.txt`
  confirms `/health`, `/entry?neutral=1`, `/partials/activation`,
  `/partials/attention`, and `/partials/launcher` from inside
  `docker-runtime-lv3`.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-portal-public-entry-r2.txt`
  confirms the public `https://ops.lv3.org/entry` edge still redirects
  unauthenticated users to the oauth2-proxy sign-in flow.
- The canonical receipt records the final release cut, generated-truth refresh,
  repository validation bundle, and the retained correction-loop evidence from
  the transient first replay failure.

## Remaining Shared Follow-Up

- None for ADR 0308, ADR 0310, or ADR 0312. The remaining shared work in this
  turn is the standard merge-to-`main`, push, and worktree cleanup sequence.
