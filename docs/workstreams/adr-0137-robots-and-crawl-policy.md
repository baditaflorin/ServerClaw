# Workstream ADR 0137: Robots And Crawl Policy

- ADR: [ADR 0137](../adr/0137-robots-and-crawl-policy.md)
- Title: shared robots.txt, global noindex headers, and apex crawl-policy coverage
- Status: merged
- Branch: `codex/adr-0137-public-surface`
- Worktree: `.worktrees/adr-0137`
- Owner: codex
- Depends On: `adr-0076-subdomain-governance`, `adr-0101-certificate-lifecycle`
- Conflicts With: none
- Shared Surfaces: `roles/nginx_edge_publication/`, `inventory/group_vars/platform.yml`, `config/certificate-catalog.json`, `mkdocs.yml`, `scripts/portal_utils.py`, `docs/runbooks/configure-edge-publication.md`

## Scope

- make `robots.txt` universal across the shared NGINX edge
- make `X-Robots-Tag: noindex, nofollow` universal across edge responses
- add robots meta tags to repository-generated HTML surfaces served directly from the edge
- cover the `lv3.org` apex in the shared edge certificate and DNS model
- add regression tests and role verification for the crawl-policy contract

## Non-Goals

- scanner-resistant hardening beyond advisory crawl controls
- login-page version suppression or other fingerprint-reduction work outside crawl policy
- live apply from this workstream

## Expected Repo Surfaces

- `docs/adr/0137-robots-and-crawl-policy.md`
- `docs/workstreams/adr-0137-robots-and-crawl-policy.md`
- `roles/nginx_edge_publication/`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/`
- `inventory/group_vars/platform.yml`
- `config/certificate-catalog.json`
- `scripts/portal_utils.py`
- `mkdocs.yml`
- `docs/theme-overrides/main.html`
- `docs/runbooks/configure-edge-publication.md`
- `docs/runbooks/developer-portal.md`

## Expected Live Surfaces

- `https://lv3.org/robots.txt` returns the shared disallow-all policy after apply from `main`
- every published `https://*.lv3.org/robots.txt` endpoint returns the same policy after apply from `main`
- published edge responses include `X-Robots-Tag: noindex, nofollow`
- repository-generated HTML surfaces include `<meta name="robots" content="noindex, nofollow">`

## Verification

- `uv run --with PyYAML --with Jinja2 --with jsonschema python -m unittest tests/test_nginx_edge_publication_role.py tests/test_changelog_portal.py tests/test_docs_site.py`
- `uv run --with-requirements requirements/docs.txt python scripts/generate_docs_site.py --write`
- `uv run --with-requirements requirements/docs.txt mkdocs build --config-file mkdocs.yml --site-dir /tmp/lv3-docs-portal-test`
- `rg -n '<meta name="robots" content="noindex, nofollow">' /tmp/lv3-docs-portal-test/index.html`

## Merge Criteria

- the edge role renders `robots.txt` without per-site exceptions
- the shared certificate definition includes `lv3.org`
- role verification checks `robots.txt`, the crawl header, and the robots meta tag
- release metadata records ADR 0137 as implemented in repository version `0.134.0`

## Outcome

- Implemented the shared crawl policy in the NGINX edge role and mirrored collection copy
- Added apex certificate and DNS coverage for `lv3.org`
- Added HTML robots meta tags to repository-generated edge surfaces
- Added focused tests and runbook verification for the crawl-policy contract

## Notes For The Next Assistant

- The repository implementation is merged, but the platform version should not advance until the public-edge and DNS automation is applied live from `main`.
- `roles/` and `collections/ansible_collections/.../roles/` must stay in sync for this surface because tests still read the legacy top-level role path.
