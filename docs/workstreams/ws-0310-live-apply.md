# Workstream ws-0310-live-apply: Live Apply ADR 0310 From Latest `origin/main`

- ADR: [ADR 0310](../adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md)
- Title: Implement the first-run activation checklist and progressive capability reveal inside the interactive ops portal, then verify the live path end to end
- Status: in_progress
- Branch: `codex/ws-0310-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0310-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal-runtime-contract`, `adr-0108-operator-onboarding-and-offboarding`, `adr-0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher`, `adr-0242-guided-human-onboarding-via-shepherd-tours`, `adr-0308-journey-aware-entry-routing-and-saved-home-selection`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0310-live-apply.md`, `docs/adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md`, `docs/adr/.index.yaml`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/operator-onboarding.md`, `docs/runbooks/windmill-operator-access-admin.md`, `.config-locations.yaml`, `config/activation-checklist.json`, `docs/schema/activation-checklist.schema.json`, `scripts/validate_repository_data_models.py`, `scripts/ops_portal/app.py`, `scripts/ops_portal/static/portal.css`, `scripts/ops_portal/templates/base.html`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/templates/partials/activation.html`, `scripts/ops_portal/templates/partials/launcher.html`, `scripts/ops_portal/templates/partials/overview.html`, `scripts/ops_portal/templates/partials/runbooks.html`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_playbook.py`, `tests/test_ops_portal_runtime_role.py`, `receipts/live-applies/2026-04-02-adr-0310-activation-checklist-live-apply.json`, `receipts/live-applies/evidence/2026-04-02-ws-0310-*`

## Purpose

Land ADR 0310 on the existing browser-first operator path without creating a
separate onboarding product: add a repo-managed activation checklist catalog,
persist checklist progress in the interactive ops portal session, and keep
advanced launcher destinations plus mutating controls hidden or disabled until
the required first-run stages are complete or explicitly revealed.

## Scope

- add the catalog and schema for first-run activation stages, links, and
  progressive reveal policy
- render the activation checklist directly inside `ops.lv3.org`
- gate admin launcher entries, mutating service actions, and mutating runbooks
  on the same server-side activation state
- sync and verify the new checklist partial through the managed ops-portal
  runtime role
- document how operator provisioning, Windmill access administration, and the
  live ops portal fit together in the first-run flow

## Expected Repo Surfaces

- `docs/adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md`
- `docs/workstreams/ws-0310-live-apply.md`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `.config-locations.yaml`
- `config/activation-checklist.json`
- `docs/schema/activation-checklist.schema.json`
- `scripts/validate_repository_data_models.py`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/partials/activation.html`
- `scripts/ops_portal/templates/partials/launcher.html`
- `scripts/ops_portal/templates/partials/overview.html`
- `scripts/ops_portal/templates/partials/runbooks.html`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_playbook.py`
- `tests/test_ops_portal_runtime_role.py`
- `workstreams.yaml`

## Expected Live Surfaces

- `https://ops.lv3.org#activation` renders the ADR 0310 checklist and preserves
  progress across normal browser-session refreshes
- launcher entries with purpose `administer` stay out of the navigable entry
  set until activation completes or the supervised reveal path is used
- mutating service actions and mutating runbooks fail closed server-side until
  the same activation guard is satisfied
- the managed ops-portal replay verifies `/partials/activation` in addition to
  the existing launcher and runtime-assurance partials

## Current Branch Status

- the activation catalog, schema, repository-data-model validation, and the
  portal server-side gating logic are implemented in this worktree
- the portal templates now surface the first-run checklist, locked launcher
  destinations, locked runbooks, and disabled service actions
- the focused portal regression slice currently passes:
  `python3 -m py_compile scripts/ops_portal/app.py` and
  `uv run --with pytest --with pyyaml --with jsonschema --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with PyJWT==2.10.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py tests/test_ops_portal_playbook.py tests/test_ops_portal.py -q`

## Remaining Work

- resync this worktree with the latest `origin/main` before the governed replay
- run the broader repo validation and automation paths from the settled branch
- live-apply `ops_portal`, capture evidence, and update the ADR metadata with
  the first verified repo/platform versions plus the implementation date
- integrate the verified change onto `main`, update protected mainline files,
  push `origin/main`, and remove the temporary worktree
