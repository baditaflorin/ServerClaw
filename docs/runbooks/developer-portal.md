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
4. generates the browser-local Pagefind bundle under `build/docs-portal/pagefind/`
5. secret-scans the generated Pagefind search artifacts before publication

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

The deploy target refreshes both shared edge static directories before publication so the docs lane does not depend on a pre-existing `build/changelog-portal/` tree.

## Verification

- `build/docs-portal/index.html` exists after `make docs`
- `build/docs-portal/services/keycloak/index.html` exists
- `build/docs-portal/reference/ports/index.html` exists
- `build/docs-portal/pagefind/pagefind-entry.json` exists
- `build/docs-portal/pagefind/pagefind-ui.js` exists
- `build/docs-portal/index.html` references `pagefind/pagefind-ui.js`
- unauthenticated `curl -Ik https://docs.lv3.org/` returns `302` to `/oauth2/sign_in`
- the rendered site carries `<meta name="robots" content="noindex, nofollow">`
- the published site returns `X-Robots-Tag: noindex, nofollow`

## Search UX Notes

- the docs header search now uses Pagefind as the browser-local index for ADRs, runbooks, generated reference pages, release notes, and the changelog
- search facets are emitted from page metadata for `section`, `audience`, `service`, `capability`, `sensitivity`, and `tag` where the corpus supports them
- `Ctrl/Cmd+K` and `/` open the search modal in the published portal
