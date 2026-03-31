# Portal Authentication By Default

This runbook verifies the shared authentication boundary for the platform's browser-facing portals.

## Protected Portals

- `ops.lv3.org`
- `changelog.lv3.org`
- `docs.lv3.org`
- `grafana.lv3.org`

## Repository Validation

Run the repository checks before a live apply:

```bash
uvx --from pyyaml python scripts/generate_platform_vars.py --check
uv run --with pyyaml python scripts/validate_portal_auth.py --validate
uv run --with pyyaml --with jsonschema python -m unittest \
  tests.test_generate_platform_vars \
  tests.test_grafana_sso_role \
  tests.test_keycloak_runtime_role \
  tests.test_nginx_edge_publication_role \
  tests.test_outline_runtime_role \
  tests.test_public_edge_oidc_auth_role \
  tests.test_session_logout_verify \
  tests.test_subdomain_catalog \
  tests.test_validate_portal_auth
```

## Live Verification

Unauthenticated requests must be blocked:

```bash
curl -Ik https://ops.lv3.org/
curl -Ik https://changelog.lv3.org/
curl -Ik https://docs.lv3.org/
curl -Ik https://grafana.lv3.org/
curl -Ik https://home.lv3.org/.well-known/lv3/session/logout
curl -Ik https://ops.lv3.org/.well-known/lv3/session/proxy-logout
curl -Ik https://ops.lv3.org/.well-known/lv3/session/logged-out
uv run --with playwright python scripts/session_logout_verify.py \
  --password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/keycloak/outline.automation-password.txt
```

Expected results:

- `ops.lv3.org`, `changelog.lv3.org`, and `docs.lv3.org` return `302` to `/oauth2/sign_in`
- `grafana.lv3.org` returns a login redirect or login page and does not serve dashboards anonymously
- `home.lv3.org/.well-known/lv3/session/logout` returns `302` to the shared `oauth2-proxy` sign-out flow
- `ops.lv3.org/.well-known/lv3/session/proxy-logout` clears the shared proxy cookie and lands on the logged-out page
- `ops.lv3.org/.well-known/lv3/session/logged-out` returns `200` with `Cache-Control: no-store`
- `scripts/session_logout_verify.py` verifies end-to-end logout on one edge-protected surface and one app-local surface
- the Outline portion of that verifier may observe the Keycloak confirmation page before logout completes; that confirmation is the currently declared product gap, and the verifier still proves the final post-logout challenge on both `home.lv3.org` and `wiki.lv3.org`

## Deployment

After regenerating any affected portal build output, apply the shared edge publication flow:

```bash
make configure-edge-publication
```

If the Keycloak broker or app-local logout consumers changed, converge them before rechecking the portals:

```bash
make converge-keycloak
HETZNER_DNS_API_TOKEN=... make live-apply-service service=outline env=production
```
