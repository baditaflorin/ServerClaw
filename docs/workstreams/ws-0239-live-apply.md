# Workstream WS-0239: Browser-Local Search Experience Via Pagefind Live Apply

- ADR: [ADR 0239](../adr/0239-browser-local-search-experience-via-pagefind.md)
- Title: Live apply browser-local docs search via Pagefind on `docs.lv3.org`
- Status: in_progress
- Implemented In Repo Version: pending main integration
- Live Applied In Platform Version: pending main replay
- Implemented On: pending
- Live Applied On: pending
- Branch: `codex/ws-0239-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0239-live-apply`
- Owner: codex
- Depends On: `adr-0094-developer-portal`, `adr-0121-local-search-and-indexing-fabric`, `adr-0135-developer-portal-sensitivity-classification`, `adr-0137-robots-and-crawl-policy`, `adr-0138-published-artifact-secret-scanning`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0239-live-apply.md`, `docs/adr/0239-browser-local-search-experience-via-pagefind.md`, `docs/adr/.index.yaml`, `docs/runbooks/developer-portal.md`, `Makefile`, `mkdocs.yml`, `requirements/docs.txt`, `scripts/generate_docs_site.py`, `scripts/build_docs_portal.py`, `scripts/validate_repo.sh`, `docs/theme-overrides/**`, `tests/test_docs_site.py`, `receipts/live-applies/2026-03-28-adr-0239-browser-local-search-live-apply.json`

## Scope

- make Pagefind the default browser-local search experience for the generated docs portal rather than leaving docs discovery on the MkDocs built-in search path
- generate the Pagefind bundle from the repo-managed docs publication workflow so `make docs`, `make deploy-docs-portal`, and generated-portal validation all converge through the same automation
- expose Pagefind filter facets for section, audience, service, capability, sensitivity, and tag where the generated corpus already carries those facts
- verify the local build, validation gate, and live edge publication end to end without mutating protected release truth on the workstream branch

## Expected Repo Surfaces

- `Makefile`
- `mkdocs.yml`
- `requirements/docs.txt`
- `scripts/generate_docs_site.py`
- `scripts/build_docs_portal.py`
- `scripts/validate_repo.sh`
- `docs/theme-overrides/main.html`
- `docs/theme-overrides/partials/header.html`
- `docs/theme-overrides/partials/search.html`
- `docs/theme-overrides/partials/content.html`
- `docs/theme-overrides/assets/stylesheets/pagefind-search.css`
- `docs/theme-overrides/assets/javascripts/pagefind-search.js`
- `docs/runbooks/developer-portal.md`
- `docs/workstreams/ws-0239-live-apply.md`
- `docs/adr/0239-browser-local-search-experience-via-pagefind.md`
- `docs/adr/.index.yaml`
- `tests/test_docs_site.py`
- `receipts/live-applies/2026-03-28-adr-0239-browser-local-search-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- `docs.lv3.org` serves the generated Pagefind bundle from `pagefind/`
- the docs header search opens a Pagefind-backed modal instead of relying on the Material built-in search runtime
- docs pages emit Pagefind filters for `section`, `audience`, `service`, `capability`, `sensitivity`, and `tag` where the page metadata provides those values
- edge publication continues to enforce authenticated access plus the existing crawl-policy and hardened response headers

## Verification Plan

- `uv run --with pytest --with-requirements requirements/docs.txt pytest -q tests/test_docs_site.py`
- `uv run --with-requirements requirements/docs.txt python3 scripts/build_docs_portal.py --generated-dir "$(mktemp -d /tmp/lv3-docs-generated.XXXXXX)" --output-dir "$(mktemp -d /tmp/lv3-docs-portal.XXXXXX)" --openapi-url ""`
- `./scripts/validate_repo.sh generated-portals agent-standards`
- `make docs`
- `make deploy-docs-portal`
- live checks on `nginx-lv3` and `docs.lv3.org` for deployed Pagefind assets, Pagefind-backed HTML wiring, and authenticated edge behaviour

## Outcome

- pending implementation and live verification

## Merge-To-Main Notes

- pending; protected integration files remain untouched on this workstream branch
