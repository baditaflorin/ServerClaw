# Workstream ws-0248-main-merge

- ADR: [ADR 0248](../adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md)
- Title: Integrate ADR 0248 session/logout authority into `origin/main`
- Status: ready_for_merge
- Included In Repo Version: pending
- Platform Version Observed During Merge: 0.130.46
- Release Date: pending
- Branch: `codex/ws-0248-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0248-main-merge`
- Owner: codex
- Depends On: `ws-0248-live-apply`

## Purpose

Carry the verified ADR 0248 shared browser-session logout contract onto the
latest `origin/main` after ADR 0252 advanced the protected mainline to
repository version `0.177.68`, keep the governed live-apply wrapper aligned
with `ready_for_merge` workstreams, cut the next protected release, replay the
integrated Keycloak, Outline, and public-edge paths from that refreshed exact-
main candidate, and refresh the canonical receipt plus release truth without
rewriting ADR 0248's first-live metadata from the earlier isolated worktree
apply.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0248-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.69.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md`
- `docs/workstreams/ws-0248-live-apply.md`
- `docs/runbooks/portal-authentication-by-default.md`
- `docs/runbooks/configure-keycloak.md`
- `docs/runbooks/configure-outline.md`
- `inventory/group_vars/platform.yml`
- `platform/interface_contracts.py`
- `scripts/generate_platform_vars.py`
- `scripts/session_logout_verify.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_grafana_sso_role.py`
- `tests/test_interface_contracts.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_outline_runtime_role.py`
- `tests/test_public_edge_oidc_auth_role.py`
- `tests/test_session_logout_verify.py`
- `playbooks/keycloak.yml`
- `playbooks/public-edge.yml`
- `playbooks/outline.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/grafana_sso/`
- `collections/ansible_collections/lv3/platform/roles/outline_runtime/`
- `receipts/live-applies/2026-03-28-adr-0248-session-logout-authority-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0248-session-logout-authority-mainline-live-apply.json`

## Verification

- pending exact-main release cut from current `origin/main`
- pending exact-main replay of the `keycloak`, `outline`, and `public-edge`
  automation paths
- pending logout verification for `home.lv3.org`, `ops.lv3.org`, and
  `wiki.lv3.org`
- pending protected-surface validation and release artifact refresh

## Outcome

- in progress
