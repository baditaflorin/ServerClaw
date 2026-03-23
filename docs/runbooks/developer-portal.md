# Developer Portal

This runbook covers the generated documentation site published at `docs.lv3.org`.

## Build

```bash
make docs
```

This command:

1. regenerates the MkDocs source tree under `docs/site-generated/`
2. snapshots the best available OpenAPI schema for the API section
3. builds the static site into `build/docs-portal/`

## Publish

The static site is published through the shared NGINX edge publication flow.

```bash
make deploy-docs-portal
```

## Verification

- `build/docs-portal/index.html` exists after `make docs`
- `build/docs-portal/services/keycloak/index.html` exists
- `build/docs-portal/reference/ports/index.html` exists
- the rendered site stays public and returns the `X-Robots-Tag: noindex` header until the platform reaches `1.0.0`
