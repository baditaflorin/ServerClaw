# Workstream ADR 0094: Developer Portal and Service Documentation Site

- ADR: [ADR 0094](../adr/0094-developer-portal-and-documentation-site.md)
- Title: MkDocs Material static site generated from platform catalogs and ADR corpus, published publicly at docs.example.com
- Status: live_applied
- Branch: `codex/adr-0094-developer-portal`
- Worktree: `../proxmox-host_server-developer-portal`
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
- configure nginx vhost `docs.example.com` — serves static site from `/srv/docs/`; no OIDC (publicly readable)
- add `docs.example.com` to `config/subdomain-catalog.json`
- update Windmill post-merge workflow to trigger `make docs && rsync site/ nginx-edge:/srv/docs/`

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
- `config/subdomain-catalog.json` (patched: `docs.example.com` added)
- Makefile (patched: `make docs` target)
- `docs/adr/0094-developer-portal-and-documentation-site.md`
- `docs/workstreams/adr-0094-developer-portal.md`

## Expected Live Surfaces

- `https://docs.example.com` is publicly accessible (no login required)
- Services directory at `https://docs.example.com/services/` lists all platform services
- ADR index at `https://docs.example.com/architecture/` lists all 111 ADRs with links
- Runbooks at `https://docs.example.com/runbooks/` render correctly
- Port reference at `https://docs.example.com/reference/ports/` lists all service ports

## Verification

- `make docs` completes with `mkdocs build --strict` exit 0 (no broken links or missing references)
- `https://docs.example.com/services/keycloak/` renders Keycloak service page with correct URL, port, and ADR link
- `https://docs.example.com/reference/ports/` contains every port from `config/service-capability-catalog.json`
- Site rebuilds and publishes automatically on the next merge to `main` after this workstream merges

## Merge Criteria

- `make docs` builds without errors
- Site is live at `https://docs.example.com`
- At minimum: index, services directory, ADR index, one runbook, and port reference are all rendered correctly
- No sensitive information (IPs, secret values, internal credentials) appears in the generated site

## Outcome

- repository implementation is complete on `main` in repo release `0.97.0`
- the docs site now builds from canonical catalogs, copied ADRs, copied runbooks, release notes, and a generated OpenAPI snapshot into `build/docs-portal/`
- `docs.example.com` is represented in the service and subdomain catalogs plus the shared edge publication defaults with a temporary `X-Robots-Tag: noindex` header
- repo release `0.105.0` hardens shared edge publication by building all portal artifacts before apply, fixes TLS SAN parsing for hostnames such as `ops.example.com`, and restores the collection-scoped mutation audit callback import path
- `docs.example.com` now resolves publicly to `203.0.113.1` from both `1.1.1.1` and the Hetzner authoritative nameserver
- HTTPS verification against the live edge returns `HTTP/2 200` for both `https://docs.example.com/` and `https://docs.example.com/services/keycloak/`, with the expected `X-Robots-Tag: noindex, nofollow, noarchive` header
- repo release `0.122.0` and platform version `0.114.7` supersede the original public-readability assumption by gating `docs.example.com` behind the shared Keycloak portal auth flow from ADR 0133
- platform version `0.105.0` is now the first live platform version where ADR 0094 is true

## Notes For The Next Assistant

- The `mkdocs-swagger-ui-tag` plugin fetches the OpenAPI schema at build time; the build must have network access to `https://api.example.com/v1/openapi.json` or the schema must be pre-fetched and saved to `docs/api/openapi.json` before the build runs
- `docs/site-generated/` should be added to `.gitignore`; only the templates and generator script are committed; the generated pages are rebuilt at publish time
- ADR rendering: copy all `docs/adr/*.md` into `docs/site-generated/architecture/decisions/` with a front-matter header added; do not modify the originals
- The nginx vhost for `docs.example.com` should add `X-Robots-Tag: noindex` header for now (prevent search engine indexing until the platform reaches 1.0.0)
