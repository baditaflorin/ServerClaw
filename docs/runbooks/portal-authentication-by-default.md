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
uv run --with pyyaml python scripts/validate_portal_auth.py --validate
uv run --with pyyaml --with jsonschema python -m unittest \
  tests.test_nginx_edge_publication_role \
  tests.test_public_edge_oidc_auth_role \
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
```

Expected results:

- `ops.lv3.org`, `changelog.lv3.org`, and `docs.lv3.org` return `302` to `/oauth2/sign_in`
- `grafana.lv3.org` returns a login redirect or login page and does not serve dashboards anonymously

## Deployment

After regenerating any affected portal build output, apply the shared edge publication flow:

```bash
make configure-edge-publication
```

If the Keycloak broker itself changed, converge it separately before rechecking the portals:

```bash
make converge-keycloak
```
