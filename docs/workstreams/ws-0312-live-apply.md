# Workstream ws-0312-live-apply: Shared Notification Center And Activity Timeline Across Human Surfaces

- ADR: [ADR 0312](../adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md)
- Title: Live apply the shared notification center and activity timeline into the interactive ops portal from the latest `origin/main`
- Status: live_applied
- Included In Repo Version: `0.177.146`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`
- Final Combined Replay Source Commit: `36e7636153e2decc324aee8d2c08bdd3d45580ae`
- Live Applied In Platform Version: `0.130.92`
- Implemented On: 2026-04-02
- Live Applied On: 2026-04-02
- Exact-Main Replay Baseline: repo `0.177.145`, platform `0.130.91`
- Branch: `codex/ws-0312-live-apply`
- Worktree: `.worktrees/ws-0312-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0307-platform-workbench-as-the-cohesive-first-party-app-frame`, `adr-0309-task-oriented-information-architecture-across-the-platform-workbench`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/app.py`, `scripts/ops_portal/static/portal.css`, `scripts/ops_portal/templates/base.html`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/templates/partials/attention.html`, `scripts/ops_portal/templates/partials/changelog.html`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/docker-compose.yml.j2`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/ops-portal.env.j2`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/ops-portal-down.md`, `docs/workstreams/ws-0312-live-apply.md`, `docs/adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md`, `docs/adr/.index.yaml`, `workstreams.yaml`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_runtime_role.py`, `tests/test_ops_portal_playbook.py`, `receipts/live-applies/2026-04-02-adr-0308-journey-entry-routing-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-*`

## Scope

- add a first live notification center to the interactive ops portal for
  actionable operator items
- add a shared activity timeline that combines recent portal-visible history
  with acknowledgement events
- persist notification acknowledge and dismiss state under the managed
  ops-portal runtime path instead of browser-only session state
- update the runtime replay, verification tasks, and operator runbooks to cover
  the new attention surface

## Outcome

- The ADR 0312 attention center and activity timeline shipped as part of the
  combined exact-main portal replay that also carried ADR 0308 and ADR 0310.
- The final exact-main replay was completed on `codex/ws-0308-live-apply-r3`
  after this workstream's portal surfaces were merged forward for shared
  closeout.
- The final guest-local verification confirmed `/partials/attention` from the
  live managed runtime and preserved the shared shell language for
  `Notification Center` plus the activity-focused copy under the same portal
  contract.
- The canonical release and live-apply metadata now record ADR 0312 as
  implemented in repository version `0.177.146` and verified live on platform
  version `0.130.92`.

## Verification

- The combined portal regression slice later passed with `60 passed`,
  preserving the attention partial, runtime-role, and playbook coverage on the
  final exact-main branch.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-live-apply-r16-0.177.146.txt`
  captures the authoritative governed production replay that promoted the
  shared attention center after the bridge-chain recovery repair.
- `receipts/live-applies/evidence/2026-04-02-ws-0308-journey-mainline-ops-portal-guest-runtime-r8.txt`
  confirms the live `Notification Center` partial from inside
  `docker-runtime-lv3`.

## Remaining Shared Follow-Up

- None. ADR 0312 is represented by the combined exact-main portal receipt and
  the merged release/platform truth on current mainline.
