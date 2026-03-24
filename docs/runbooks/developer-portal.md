# Developer Portal

- Sensitivity: INTERNAL
- Portal Summary: Build, publish, and verify the generated developer portal, including page-level sensitivity tagging.

This runbook covers the generated documentation site published at `docs.lv3.org`.

## Build

```bash
make docs
```

This command:

1. regenerates the MkDocs source tree under `docs/site-generated/`
2. snapshots the best available OpenAPI schema for the API section
3. builds the static site into `build/docs-portal/`

## Sensitivity Classification

ADR and runbook pages can declare portal sensitivity in either YAML frontmatter (`sensitivity`) or the existing top metadata block (`- Sensitivity:`).

- documents with no explicit sensitivity default to `INTERNAL`
- `RESTRICTED` documents are rendered as summary-only pages in the generated portal
- `CONFIDENTIAL` documents stay source-only and are omitted from the published portal output

If a restricted document needs a safe summary, add `portal_summary` in frontmatter or `- Portal Summary:` in the metadata block instead of relying on body text.

## Publish

The static site is published through the shared NGINX edge publication flow.

```bash
make deploy-docs-portal
```

## Verification

- `build/docs-portal/index.html` exists after `make docs`
- `build/docs-portal/services/keycloak/index.html` exists
- `build/docs-portal/reference/ports/index.html` exists
- unauthenticated `curl -Ik https://docs.lv3.org/` returns `302` to `/oauth2/sign_in`
- the authenticated site still returns the `X-Robots-Tag: noindex` header until the platform reaches `1.0.0`
