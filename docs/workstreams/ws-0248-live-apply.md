# Workstream WS-0248: Session And Logout Authority Live Apply

- ADR: [ADR 0248](../adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md)
- Title: Live apply unified browser-session logout authority across Keycloak, oauth2-proxy, and app-local sign-out surfaces
- Status: in-progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0248-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0248-live-apply`
- Owner: codex
- Depends On: `adr-0056-keycloak-for-operator-and-agent-sso`, `adr-0133-portal-authentication-by-default`, `adr-0199-outline-living-knowledge-wiki`, `adr-0247-authenticated-browser-journey-verification-via-playwright`
- Conflicts With: none
- Shared Surfaces: `inventory/group_vars/platform.yml`, `playbooks/keycloak.yml`, `playbooks/public-edge.yml`, `playbooks/outline.yml`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/**`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/**`, `collections/ansible_collections/lv3/platform/roles/grafana_sso/**`, `collections/ansible_collections/lv3/platform/roles/outline_runtime/**`, `docs/runbooks/portal-authentication-by-default.md`, `docs/runbooks/configure-keycloak.md`, `docs/runbooks/configure-outline.md`, `scripts/session_logout_verify.py`, `tests/test_nginx_edge_publication_role.py`, `tests/test_keycloak_runtime_role.py`, `tests/test_session_logout_verify.py`, `docs/adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md`, `workstreams.yaml`

## Scope

- make Keycloak the effective logout authority for the shared edge-protected browser estate
- ensure oauth2-proxy logout clears its session cookie and uses Keycloak RP-initiated logout with an `id_token_hint` so browser logout does not stall on a confirmation page
- align app-local logout surfaces that already manage their own local session state with the same shared logout authority path
- record live-apply evidence, branch-local verification, and merge-to-main notes without mutating protected release truth on this workstream branch

## Expected Repo Surfaces

- `inventory/group_vars/platform.yml`
- `playbooks/keycloak.yml`
- `playbooks/public-edge.yml`
- `playbooks/outline.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/grafana_sso/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/outline_runtime/defaults/main.yml`
- `docs/runbooks/portal-authentication-by-default.md`
- `docs/runbooks/configure-keycloak.md`
- `docs/runbooks/configure-outline.md`
- `scripts/generate_platform_vars.py`
- `docs/workstreams/ws-0248-live-apply.md`
- `docs/adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md`
- `scripts/session_logout_verify.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_grafana_sso_role.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_outline_runtime_role.py`
- `tests/test_session_logout_verify.py`
- `receipts/live-applies/2026-03-28-adr-0248-session-logout-authority-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- edge-protected services expose a repo-managed shared logout entrypoint that clears the shared oauth2-proxy cookie and completes Keycloak logout without an interactive confirmation page
- `ops.lv3.org` serves both a repo-managed proxy-cleanup path and a logged-out landing path for post-logout return
- Grafana local logout hands off to Keycloak first and then to the shared proxy-cleanup path so both the app-local session and shared edge cookie are cleared
- Outline local logout hands off to Keycloak with the same shared proxy-cleanup return path so app-local and shared-edge logout semantics stay aligned
- revisiting a protected surface after logout yields the expected unauthenticated redirect or challenge path instead of silent re-entry

## Verification

- repo checks for the affected role templates and logout verifier
- syntax checks for `keycloak`, `public-edge`, and `outline`
- branch-local live convergence from latest `origin/main`
- end-to-end browser-session verification on at least one shared edge-protected surface and one app-local logout surface
- receipt recorded under `receipts/live-applies/`

## Merge-To-Main Notes

- branch-local work must not change `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml`
- if the live apply succeeds before merge, update ADR 0248 metadata here and in the ADR, then carry the protected integration-file updates only during the final merge-to-main step
