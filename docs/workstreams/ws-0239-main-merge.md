# Workstream ws-0239-main-merge

- ADR: [ADR 0239](../adr/0239-browser-local-search-experience-via-pagefind.md)
- Title: Integrate ADR 0239 browser-local search into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.62
- Platform Version Observed During Merge: 0.130.45
- Release Date: 2026-03-29
- Branch: `codex/ws-0239-main-merge-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0239-main-merge-r2`
- Owner: codex
- Depends On: `ws-0239-live-apply`

## Purpose

Carry the verified ADR 0239 Pagefind implementation onto the latest
`origin/main`, cut the next repository patch release from the current mainline
baseline, replay the docs-portal publication from the refreshed mainline
candidate, and refresh the protected canonical-truth surfaces once the exact
main replay is re-verified.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0239-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.62.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/.index.yaml`
- `docs/adr/0239-browser-local-search-experience-via-pagefind.md`
- `docs/workstreams/ws-0239-live-apply.md`
- `docs/runbooks/deployment-history-portal.md`
- `docs/runbooks/developer-portal.md`
- `docs/site-generated/architecture/dependency-graph.md`
- `Makefile`
- `mkdocs.yml`
- `requirements/docs.txt`
- `scripts/generate_docs_site.py`
- `scripts/build_docs_portal.py`
- `scripts/validate_repo.sh`
- `docs/theme-overrides/`
- `tests/test_docs_site.py`
- `receipts/live-applies/2026-03-28-adr-0239-browser-local-search-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0239-browser-local-search-mainline-live-apply.json`

## Verification

- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.45 after the exact-main ADR 0239 replay re-verifies Pagefind-backed browser-local docs search on docs.lv3.org while preserving the authenticated edge contract on top of the 0.130.44 baseline" --dry-run`
  reported `Current version: 0.177.61`, `Next version: 0.177.62`, and
  `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.45 after the exact-main ADR 0239 replay re-verifies Pagefind-backed browser-local docs search on docs.lv3.org while preserving the authenticated edge contract on top of the 0.130.44 baseline"`
  prepared release `0.177.62`
- `uv run --with pytest --with-requirements requirements/docs.txt pytest -q tests/test_docs_site.py`
  returned `7 passed`
- `uv run --with-requirements requirements/docs.txt python3 scripts/build_docs_portal.py --generated-dir "$(mktemp -d /tmp/lv3-docs-generated.XXXXXX)" --output-dir "$(mktemp -d /tmp/lv3-docs-portal.XXXXXX)" --openapi-url ""`
  completed successfully and built the Pagefind bundle in a temp publication
  tree
- `make docs` completed successfully, including the published-artifact secret
  scan for `build/docs-portal`
- `make deploy-docs-portal` completed successfully from the rebased `0.177.62`
  candidate and re-published both the changelog and docs portal directories on
  `nginx-lv3`
- `curl -ksSI https://docs.lv3.org/` returned `HTTP/2 302` with
  `location: https://docs.lv3.org/oauth2/sign_in?rd=https://docs.lv3.org/` and
  `x-robots-tag: noindex, nofollow`
- guest-local verification on `nginx-lv3` confirmed the published
  `pagefind/pagefind-entry.json`, `pagefind/pagefind-ui.js`,
  `pagefind/pagefind-ui.css`, the `0.177.62` release page, the Pagefind search
  modal markup on the home page, and `data-pagefind-filter="section"` on the
  dependency-graph page without the raw frontmatter leak

## Outcome

- release `0.177.62` carries ADR 0239 onto `main`
- the current live platform baseline after the exact-main replay is `0.130.45`
- the exact-main evidence is recorded under
  `receipts/live-applies/2026-03-29-adr-0239-browser-local-search-mainline-live-apply.json`
