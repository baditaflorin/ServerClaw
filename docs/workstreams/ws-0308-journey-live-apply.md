# Workstream ws-0308-journey-live-apply: Live Apply ADR 0308 Journey Routing From Latest `origin/main`

- ADR: [ADR 0308](../adr/0308-journey-aware-entry-routing-and-saved-home-selection.md)
- Title: Ship the journey-aware entry router, saved-home selection, and activation-first start surface on the interactive ops portal
- Status: ready
- Branch: `codex/ws-0308-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0308-live-apply-r2`
- Owner: codex
- Depends On: `adr-0093`, `adr-0152`, `adr-0235`, `adr-0242`, `adr-0313`
- Conflicts With: `ws-0308-live-apply`
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0308-journey-live-apply.md`, `docs/workstreams/adr-0307-platform-app-cohesion-bundle.md`, `docs/adr/0308-journey-aware-entry-routing-and-saved-home-selection.md`, `docs/runbooks/platform-operations-portal.md`, `scripts/ops_portal/app.py`, `scripts/ops_portal/templates/base.html`, `scripts/ops_portal/templates/entry.html`, `scripts/ops_portal/templates/index.html`, `scripts/ops_portal/static/portal.css`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal_runtime_role.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

## Purpose

Implement the journey-aware entry-routing ADR on top of the latest realistic
`origin/main` portal runtime so authenticated operators land on the right
surface in the right order:

1. a permitted deep link
2. unfinished activation work
3. a pinned home
4. a role-derived default home
5. the neutral start surface

## Scope

- add a neutral `/entry` route to the interactive ops portal runtime
- store activation and saved-home state in durable browser cookies
- infer viewer/operator/admin entry mode from the authenticated portal session
- expose curated home choices for Homepage, Ops Portal, Docs, and Changelog
- document the operational verification path and preserve live-apply evidence

## Non-Goals

- changing authorization or bypassing role checks through a saved home
- replacing the shared launcher or the ADR 0313 contextual-help drawer
- reusing the existing `ws-0308-live-apply` registry key, which already belongs
  to the unrelated operator-provisioning ADR that also uses number `0308`

## Expected Repo Surfaces

- `docs/adr/0308-journey-aware-entry-routing-and-saved-home-selection.md`
- `docs/workstreams/ws-0308-journey-live-apply.md`
- `docs/workstreams/adr-0307-platform-app-cohesion-bundle.md`
- `docs/runbooks/platform-operations-portal.md`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/entry.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/static/portal.css`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `workstreams.yaml`
- `receipts/live-applies/`
- `receipts/live-applies/evidence/`

## Expected Live Surfaces

- `https://ops.lv3.org/entry` renders the journey-aware start surface after the
  oauth2-proxy sign-in flow
- first-run operators cannot pin a saved home until the activation checklist is
  completed or skipped
- a pinned home overrides the role-derived default home, while explicit deep
  links still win for the current request
- repo-managed runtime verification fails closed if the `/entry?neutral=1`
  surface disappears during a future replay

## Verification Plan

- `python3 -m py_compile scripts/ops_portal/app.py`
- `uv run --with pytest --with pyyaml --with jsonschema --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with PyJWT==2.10.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py tests/test_ops_portal.py tests/test_runtime_assurance_scoreboard.py -q`
- `make syntax-check-ops-portal`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh workstream-surfaces`
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=ops_portal env=production EXTRA_ARGS='-e bypass_promotion=true -e ops_portal_repo_root=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0308-live-apply-r2'`

## Notes

- `origin/main` already contains another `ADR 0308` document and an existing
  `ws-0308-live-apply` entry for the operator-provisioning execution-surface
  workstream. This workstream keeps the requested ADR file path but uses the
  unique registry key `ws-0308-journey-live-apply` so the workstream registry
  stays merge-safe.
