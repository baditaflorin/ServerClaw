# Workstream ADR 0133: Portal Authentication By Default

- ADR: [ADR 0133](../adr/0133-portal-authentication-by-default.md)
- Title: Enforce Keycloak-backed authentication by default for portal services
- Status: merged
- Branch: `codex/adr-0133-portal-auth-default`
- Worktree: `.worktrees/adr-0133-auth-default`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0056-keycloak-sso`, `adr-0074-ops-portal`, `adr-0081-changelog-portal`, `adr-0094-developer-portal`
- Conflicts With: none
- Shared Surfaces: `config/subdomain-catalog.json`, `roles/nginx_edge_publication`, `roles/public_edge_oidc_auth`, `roles/grafana_sso`, `docs/runbooks/`

## Scope

- add explicit portal auth classification to the governed subdomain catalog
- validate the classification with a dedicated `scripts/validate_portal_auth.py` policy check
- protect `docs.example.com` and `changelog.example.com` with the shared edge `oauth2-proxy`
- expand the shared portal auth cookie scope to `.example.com` so one Keycloak session covers all protected portals
- preserve Grafana's Keycloak login path while keeping anonymous access disabled
- verify that unauthenticated requests no longer reach protected portal content

## Expected Repo Surfaces

- `docs/adr/0133-portal-authentication-by-default.md`
- `docs/workstreams/adr-0133-portal-authentication-by-default.md`
- `docs/runbooks/portal-authentication-by-default.md`
- `config/subdomain-catalog.json`
- `docs/schema/subdomain-catalog.schema.json`
- `scripts/subdomain_catalog.py`
- `scripts/validate_portal_auth.py`
- `scripts/validate_repo.sh`
- `roles/nginx_edge_publication/defaults/main.yml`
- `roles/public_edge_oidc_auth/defaults/main.yml`

## Expected Live Surfaces

- `https://ops.example.com/` redirects unauthenticated requests to the Keycloak sign-in flow
- `https://changelog.example.com/` redirects unauthenticated requests to the Keycloak sign-in flow
- `https://docs.example.com/` redirects unauthenticated requests to the Keycloak sign-in flow
- `https://grafana.example.com/` blocks anonymous dashboard access

## Verification

- `uv run --with pyyaml python scripts/validate_portal_auth.py --validate`
- `uv run --with pyyaml --with jsonschema python -m unittest tests.test_nginx_edge_publication_role tests.test_public_edge_oidc_auth_role tests.test_subdomain_catalog tests.test_validate_portal_auth`
- `curl -Ik https://ops.example.com/`
- `curl -Ik https://changelog.example.com/`
- `curl -Ik https://docs.example.com/`
- `curl -Ik https://grafana.example.com/`

## Outcome

- repository implementation is complete on `main` in repo release `0.130.0`
- the shared edge auth proxy now protects `ops.example.com`, `changelog.example.com`, and `docs.example.com` with a shared `.example.com` session cookie
- the governed subdomain catalog now records explicit auth posture for every hostname and rejects undocumented public exceptions
- platform version `0.114.7` is the first live platform version where ADR 0133 is true
