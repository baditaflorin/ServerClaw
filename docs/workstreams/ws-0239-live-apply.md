# Workstream WS-0239: Browser-Local Search Experience Via Pagefind Live Apply

- ADR: [ADR 0239](../adr/0239-browser-local-search-experience-via-pagefind.md)
- Title: Live apply browser-local docs search via Pagefind on `docs.example.com`
- Status: live_applied
- Implemented In Repo Version: 0.177.62
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0239-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0239-live-apply`
- Owner: codex
- Depends On: `adr-0094-developer-portal`, `adr-0121-local-search-and-indexing-fabric`, `adr-0135-developer-portal-sensitivity-classification`, `adr-0137-robots-and-crawl-policy`, `adr-0138-published-artifact-secret-scanning`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0239-live-apply.md`, `docs/adr/0239-browser-local-search-experience-via-pagefind.md`, `docs/adr/.index.yaml`, `docs/runbooks/developer-portal.md`, `docs/runbooks/deployment-history-portal.md`, `docs/site-generated/architecture/dependency-graph.md`, `Makefile`, `mkdocs.yml`, `requirements/docs.txt`, `scripts/generate_docs_site.py`, `scripts/build_docs_portal.py`, `scripts/validate_repo.sh`, `docs/theme-overrides/**`, `tests/test_docs_site.py`, `receipts/live-applies/2026-03-28-adr-0239-browser-local-search-live-apply.json`

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

- `docs.example.com` serves the generated Pagefind bundle from `pagefind/`
- the docs header search opens a Pagefind-backed modal instead of relying on the Material built-in search runtime
- docs pages emit Pagefind filters for `section`, `audience`, `service`, `capability`, `sensitivity`, and `tag` where the page metadata provides those values
- edge publication continues to enforce authenticated access plus the existing crawl-policy and hardened response headers

## Verification Plan

- `uv run --with pytest --with-requirements requirements/docs.txt pytest -q tests/test_docs_site.py`
- `uv run --with-requirements requirements/docs.txt python3 scripts/build_docs_portal.py --generated-dir "$(mktemp -d /tmp/lv3-docs-generated.XXXXXX)" --output-dir "$(mktemp -d /tmp/lv3-docs-portal.XXXXXX)" --openapi-url ""`
- `./scripts/validate_repo.sh generated-portals workstream-surfaces agent-standards`
- `make docs`
- `make deploy-docs-portal`
- live checks on `nginx-edge` and `docs.example.com` for deployed Pagefind assets, Pagefind-backed HTML wiring, and authenticated edge behaviour

## Live Apply Outcome

- `make deploy-docs-portal` now refreshes both shared edge static directories before publication, fixing the repo automation gap where the shared `public-edge` lane failed when `build/changelog-portal/` was absent locally
- `make docs` now renders the docs portal through `scripts/build_docs_portal.py`, which builds the MkDocs site, generates the Pagefind bundle under `build/docs-portal/pagefind/`, and secret-scans the published search artifacts before publication
- the docs theme now opens a Pagefind-backed modal from the header search control and emits Pagefind filters for `section`, `audience`, `service`, `capability`, `sensitivity`, and `tag` across the generated docs corpus
- live verification on `nginx-edge` confirmed `pagefind/pagefind-entry.json`, `pagefind/pagefind-ui.js`, and `pagefind/pagefind-ui.css` on the published docs tree, while the deployed HTML carries `pagefind/pagefind-ui.js`, `id="pagefind-search"`, and `data-pagefind-filter="section"` without the earlier dependency-graph frontmatter leak
- external verification confirmed `https://docs.example.com/` still returns `302` to `/oauth2/sign_in` with `X-Robots-Tag: noindex, nofollow`, preserving the existing authenticated edge contract while serving the new browser-local search assets behind the auth gate

## Mainline Integration Notes

- release `0.177.62` is the first merged repo version that carries ADR 0239 on
  `origin/main`
- the exact-main replay on `2026-03-29` re-verified the authenticated edge
  redirect plus the published Pagefind assets under receipt
  `2026-03-29-adr-0239-browser-local-search-mainline-live-apply.json`
- a latest-server check later on `2026-03-29` found `nginx-edge` had drifted
  back to the older docs bundle without the Pagefind publication, so the merged
  mainline commit `48b8a79b02480f3cefa1b76e1e5ba88db9098cc6` was replayed again
  under receipt `2026-03-29-adr-0239-browser-local-search-post-merge-replay.json`
- the current live platform baseline after that exact-main replay is
  `0.130.45`
