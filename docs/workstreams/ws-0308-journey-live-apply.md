# Workstream ws-0308-journey-live-apply: Live Apply ADR 0308 Journey Routing From Latest `origin/main`

- ADR: [ADR 0308](../adr/0308-journey-aware-entry-routing-and-saved-home-selection.md)
- Title: Ship the journey-aware entry router, saved-home selection, activation-first start surface, and the integrated attention-first portal shell on the interactive ops portal
- Status: live_applied
- Included In Repo Version: `0.177.146`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`
- Final Replay Source Commit: `36e7636153e2decc324aee8d2c08bdd3d45580ae`
- Live Applied In Platform Version: `0.130.92`
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.145`, platform `0.130.91`
- Branch: `codex/ws-0308-live-apply-r3`
- Worktree: `.worktrees/ws-0308-live-apply-r2`
- Owner: codex
- Depends On: `adr-0093`, `adr-0152`, `adr-0235`, `adr-0242`, `adr-0310`, `adr-0312`, `adr-0313`
- Conflicts With: `ws-0308-live-apply`
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0308-journey-live-apply.md`, `docs/workstreams/adr-0307-platform-app-cohesion-bundle.md`, `docs/adr/0308-journey-aware-entry-routing-and-saved-home-selection.md`, `docs/adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md`, `docs/adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md`, `docs/adr/.index.yaml`, `docs/runbooks/platform-operations-portal.md`, `scripts/ops_portal/app.py`, `scripts/ops_portal/templates/base.html`, `scripts/ops_portal/templates/entry.html`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/templates/partials/activation.html`, `scripts/ops_portal/templates/partials/attention.html`, `scripts/ops_portal/templates/partials/launcher.html`, `scripts/ops_portal/static/portal.css`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `platform/ansible/execution_scopes.py`, `scripts/ansible_scope_runner.py`, `tests/test_ansible_execution_scopes.py`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_playbook.py`, `tests/test_ops_portal_runtime_role.py`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/site-generated/architecture/dependency-graph.md`, `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-*`, `receipts/restic-backups/20260402T131708Z.json`, `receipts/restic-backups/20260402T154404Z.json`, `receipts/restic-snapshots-latest.json`, `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`

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
- preserve the exact-main live-apply evidence, release-truth update, backup
  receipt, and refreshed SBOM for the final combined replay

## Outcome

- The final exact-main integration promoted the combined portal change to
  repository version `0.177.146` and platform version `0.130.92` from the
  latest realistic baseline `0.177.145 / 0.130.91`.
- The first refreshed exact-main replay truthfully failed closed in
  `...live-apply-r14-0.177.146.txt` because the Docker `nat` `DOCKER` chain was
  still missing after guest firewall evaluation, which would have broken
  published ports if left untreated.
- The bridge-chain recovery repair landed at source commit
  `36e7636153e2decc324aee8d2c08bdd3d45580ae`, and the final governed replay
  then completed successfully with recap
  `docker-runtime-lv3 : ok=198 changed=11 unreachable=0 failed=0 skipped=36 rescued=0 ignored=0`.
- The integrated runtime now serves the journey-aware neutral start surface, the
  first-run activation checklist, the shared notification center, and the
  launcher/search shell from the same governed production deployment.
- The replay refreshed the governed restic config-backup receipt
  `receipts/restic-backups/20260402T154404Z.json`, updated
  `receipts/restic-snapshots-latest.json`, and regenerated the host SBOM at
  `receipts/sbom/host-docker-runtime-lv3-2026-04-02.cdx.json`.

## Verification

- The focused regression slice later passed with `60 passed` across the
  interactive portal runtime, playbook, runtime-role, scoped execution, and
  guest-firewall tests from the same branch that carried the final replay.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-live-apply-r14-0.177.146.txt`
  preserves the real exact-main failure that exposed missing Docker bridge
  chains during the replay.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-live-apply-r16-0.177.146.txt`
  captures the authoritative governed production replay after the recovery
  repair landed.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-ops-portal-guest-runtime-r8.txt`
  confirms `/health`, `/entry?neutral=1`, `/partials/activation`,
  `/partials/attention`, and `/partials/launcher` from inside
  `docker-runtime-lv3`, including the saved-home pin, redirect, and clear flow.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-portal-public-entry-r3.txt`
  confirms the public `https://ops.lv3.org/entry` edge still redirects
  unauthenticated users to the oauth2-proxy sign-in flow.
- `receipts/restic-backups/20260402T154404Z.json` and
  `receipts/restic-snapshots-latest.json` preserve the refreshed governed
  restic backup state from the successful replay.

## Remaining Shared Follow-Up

- None. This workstream now records the final exact-main portal replay used for
  merge to `main`, push to `origin/main`, and worktree cleanup.
