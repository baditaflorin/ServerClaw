# Workstream WS-0234: PatternFly Human Shell Live Apply

- ADR: [ADR 0234](../adr/0234-shared-human-app-shell-and-navigation-via-patternfly.md)
- Title: Live apply the shared human app shell and navigation contract on the
  interactive ops portal
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0234-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0234-live-apply-r2`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`,
  `adr-0133-portal-authentication-by-default`,
  `adr-0209-use-case-services-and-thin-delivery-adapters`
- Conflicts With: none
- Shared Surfaces: `scripts/ops_portal/`, `docs/adr/0234-*`,
  `docs/runbooks/ops-portal-down.md`,
  `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`,
  `tests/test_interactive_ops_portal.py`,
  `tests/test_nginx_edge_publication_role.py`,
  `tests/test_security_headers_audit.py`, `workstreams.yaml`

## Scope

- move the live interactive ops portal from repo-local hero chrome to a
  PatternFly-based shared shell
- add the ADR-required masthead, responsive primary navigation, shared section
  templates, and shared state primitives for warnings, errors, unauthorized
  states, and loading transitions
- keep product-native tools as linked destinations rather than embedding them
  into one page shell
- update the published `ops.lv3.org` CSP so the browser can load the pinned
  PatternFly stylesheet bundle
- verify the guest-local and published portal surfaces end to end and record a
  durable receipt before merge-to-main truth updates

## Non-Goals

- rewriting Homepage, Outline, Plane, Grafana, or other product-native UIs
- implementing ADR 0235 favorites and recent-destination behavior in the same
  change
- updating protected release truth on this workstream branch before the final
  integration step

## Expected Repo Surfaces

- `docs/workstreams/ws-0234-live-apply.md`
- `docs/adr/0234-shared-human-app-shell-and-navigation-via-patternfly.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/ops-portal-down.md`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/static/portal.js`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/macros/states.html`
- `scripts/ops_portal/templates/partials/action_result.html`
- `scripts/ops_portal/templates/partials/agents.html`
- `scripts/ops_portal/templates/partials/changelog.html`
- `scripts/ops_portal/templates/partials/drift.html`
- `scripts/ops_portal/templates/partials/overview.html`
- `scripts/ops_portal/templates/partials/runbooks.html`
- `scripts/ops_portal/templates/partials/search.html`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_security_headers_audit.py`
- `receipts/live-applies/2026-03-28-adr-0234-patternfly-shell-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `ops.lv3.org` renders a PatternFly shell with a shared masthead, responsive
  navigation, and consistent status-state components
- `docker-runtime-lv3` serves the same shell on the guest-local ops portal
  listener
- the published edge security policy allows the pinned PatternFly stylesheet
  while keeping the portal auth-gated and same-origin for the repo-managed JS
  shell helpers

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest -q tests/test_interactive_ops_portal.py tests/test_nginx_edge_publication_role.py tests/test_security_headers_audit.py`
- `make syntax-check-ops-portal`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh workstream-surfaces`
- live replay from this isolated worktree for the ops portal runtime and the
  shared edge publication path, followed by guest-local and published-browser
  verification

## Notes For The Next Assistant

- the live portal runtime is the first concrete ADR 0234 surface; keep follow-up
  work focused on extending the same shell primitives rather than cloning them
  into a second custom layout
- if the page loads unstyled after deploy, check the ops portal CSP first
  because the shared shell depends on the pinned PatternFly asset URL
- the protected `README.md`, `VERSION`, `changelog.md`, `versions/stack.yaml`,
  and release-note updates still belong to the final integration step
