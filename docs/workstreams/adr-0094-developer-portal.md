# Workstream ADR 0094: Developer Portal and Service Documentation Site

- ADR: [ADR 0094](../adr/0094-developer-portal-and-documentation-site.md)
- Title: MkDocs Material static site generated from platform catalogs and ADR corpus, published publicly at docs.lv3.org
- Status: merged
- Branch: `codex/adr-0094-developer-portal`
- Worktree: `../proxmox_florin_server-developer-portal`
- Owner: codex
- Depends On: `adr-0021-nginx-edge`, `adr-0033-service-catalog`, `adr-0076-subdomain-governance`, `adr-0081-changelog`, `adr-0092-platform-api-gateway`
- Conflicts With: none
- Shared Surfaces: `config/service-capability-catalog.json`, `docs/adr/`, `changelog.md`, nginx edge config

## Scope

- write `scripts/generate_docs_site.py` — generates service pages, reference tables, and port/subdomain references from catalog JSON
- write `mkdocs.yml` — MkDocs Material configuration
- write `requirements/docs.txt` — MkDocs + plugins (material, swagger-ui-tag)
- write template files `docs/templates/` — Jinja2 templates for generated pages
- write initial runbooks: `docs/runbooks/deploy-a-service.md`, `docs/runbooks/rotate-certificates.md`, `docs/runbooks/add-a-new-service.md`, `docs/runbooks/break-glass-recovery.md`
- write `docs/index.md` — platform overview and quick-start
- add `make docs` target — runs generator + `mkdocs build --strict`
- configure nginx vhost `docs.lv3.org` — serves static site from `/srv/docs/`; no OIDC (publicly readable)
- add `docs.lv3.org` to `config/subdomain-catalog.json`
- update Windmill post-merge workflow to trigger `make docs && rsync site/ nginx-lv3:/srv/docs/`

## Non-Goals

- Real-time platform status in the docs site (that belongs to ops portal)
- User-editable wiki (static site only)
- Multi-language documentation

## Expected Repo Surfaces

- `mkdocs.yml`
- `requirements/docs.txt`
- `scripts/generate_docs_site.py`
- `docs/templates/` (Jinja2 templates for generated pages)
- `docs/index.md`
- `docs/runbooks/` (4 initial runbooks)
- `docs/site-generated/` (generated output; `.gitignore`d except `.gitkeep`)
- `config/subdomain-catalog.json` (patched: `docs.lv3.org` added)
- Makefile (patched: `make docs` target)
- `docs/adr/0094-developer-portal-and-documentation-site.md`
- `docs/workstreams/adr-0094-developer-portal.md`

## Expected Live Surfaces

- `https://docs.lv3.org` is publicly accessible (no login required)
- Services directory at `https://docs.lv3.org/services/` lists all platform services
- ADR index at `https://docs.lv3.org/architecture/` lists all 111 ADRs with links
- Runbooks at `https://docs.lv3.org/runbooks/` render correctly
- Port reference at `https://docs.lv3.org/reference/ports/` lists all service ports

## Verification

- `make docs` completes with `mkdocs build --strict` exit 0 (no broken links or missing references)
- `https://docs.lv3.org/services/keycloak/` renders Keycloak service page with correct URL, port, and ADR link
- `https://docs.lv3.org/reference/ports/` contains every port from `config/service-capability-catalog.json`
- Site rebuilds and publishes automatically on the next merge to `main` after this workstream merges

## Merge Criteria

- `make docs` builds without errors
- Site is live at `https://docs.lv3.org`
- At minimum: index, services directory, ADR index, one runbook, and port reference are all rendered correctly
- No sensitive information (IPs, secret values, internal credentials) appears in the generated site

## Outcome

- repository implementation is complete on `main` in repo release `0.97.0`
- the docs site now builds from canonical catalogs, copied ADRs, copied runbooks, release notes, and a generated OpenAPI snapshot into `build/docs-portal/`
- `docs.lv3.org` is represented in the service and subdomain catalogs plus the shared edge publication defaults with a temporary `X-Robots-Tag: noindex` header
- repo release `0.105.0` hardens shared edge publication by building all portal artifacts before apply, fixes TLS SAN parsing for hostnames such as `ops.lv3.org`, and restores the collection-scoped mutation audit callback import path
- edge publication was verified directly against `65.108.75.123` with `--resolve` and serves the docs portal with the expected `X-Robots-Tag: noindex` header, but public DNS for `docs.lv3.org` still needs to resolve before this workstream can be marked `live_applied`
- no live platform version change is claimed yet; public publication still requires an apply from `main`

## Notes For The Next Assistant

- The `mkdocs-swagger-ui-tag` plugin fetches the OpenAPI schema at build time; the build must have network access to `https://api.lv3.org/v1/openapi.json` or the schema must be pre-fetched and saved to `docs/api/openapi.json` before the build runs
- `docs/site-generated/` should be added to `.gitignore`; only the templates and generator script are committed; the generated pages are rebuilt at publish time
- ADR rendering: copy all `docs/adr/*.md` into `docs/site-generated/architecture/decisions/` with a front-matter header added; do not modify the originals
- The nginx vhost for `docs.lv3.org` should add `X-Robots-Tag: noindex` header for now (prevent search engine indexing until the platform reaches 1.0.0)
