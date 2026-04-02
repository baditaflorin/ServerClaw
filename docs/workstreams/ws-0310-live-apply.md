# Workstream ws-0310-live-apply: Live Apply ADR 0310 From Latest `origin/main`

- ADR: [ADR 0310](../adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md)
- Title: Implement the first-run activation checklist and progressive capability reveal inside the interactive ops portal, then verify the live path end to end
- Status: live_applied
- Included In Repo Version: `0.177.144`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`
- Live Applied In Platform Version: `0.130.91`
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.143`, platform `0.130.90`
- Branch: `codex/ws-0310-live-apply`
- Worktree: `.worktrees/ws-0310-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal-runtime-contract`, `adr-0108-operator-onboarding-and-offboarding`, `adr-0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher`, `adr-0242-guided-human-onboarding-via-shepherd-tours`, `adr-0308-journey-aware-entry-routing-and-saved-home-selection`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0310-live-apply.md`, `docs/adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md`, `docs/adr/.index.yaml`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/operator-onboarding.md`, `docs/runbooks/windmill-operator-access-admin.md`, `.config-locations.yaml`, `config/activation-checklist.json`, `docs/schema/activation-checklist.schema.json`, `scripts/validate_repository_data_models.py`, `scripts/ops_portal/app.py`, `scripts/ops_portal/static/portal.css`, `scripts/ops_portal/templates/base.html`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/templates/partials/activation.html`, `scripts/ops_portal/templates/partials/launcher.html`, `scripts/ops_portal/templates/partials/overview.html`, `scripts/ops_portal/templates/partials/runbooks.html`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_playbook.py`, `tests/test_ops_portal_runtime_role.py`, `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-*`

## Purpose

Land ADR 0310 on the browser-first operator path without creating a separate
onboarding product: keep the activation checklist catalog, progress model, and
progressive-reveal policy inside the interactive ops portal and verify the live
runtime path from the latest synchronized mainline.

## Outcome

- The ADR 0310 activation catalog, first-run checklist, locked launcher
  destinations, and guarded mutating paths were integrated into the same
  exact-main replay that promoted ADR 0308 and ADR 0312.
- The final exact-main replay was completed on `codex/ws-0308-live-apply-r3`
  after this workstream's portal surfaces were merged forward for shared
  closeout.
- The final combined replay and guest-local verification proved that
  `/partials/activation` is present on the live managed runtime and still
  renders the first-run checklist copy and the progressive capability reveal
  guidance.
- The merged release cut records ADR 0310 as implemented in repository version
  `0.177.144`, with the live platform proof anchored to platform version
  `0.130.91`.

## Verification

- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-targeted-tests-r3.txt`
  covers the focused `tests/test_interactive_ops_portal.py`,
  `tests/test_ops_portal_runtime_role.py`, and
  `tests/test_ops_portal_playbook.py` slice that exercises the activation
  gates.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-live-apply-r6-combined.txt`
  captures the governed production replay that published the merged portal
  surface.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-ops-portal-guest-runtime-r4.txt`
  confirms the live `First-Run Activation` partial and its guarded copy from
  inside `docker-runtime-lv3`.

## Remaining Shared Follow-Up

- None. ADR 0310 is carried by the combined canonical portal receipt and the
  final integration release surfaces.
