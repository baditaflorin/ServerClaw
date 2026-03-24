# Workstream ADR 0135: Developer Portal Sensitivity Classification

- ADR: [ADR 0135](../adr/0135-developer-portal-sensitivity-classification.md)
- Title: sensitivity-tagged developer-portal pages with summary-only restricted documents and source-only confidential documents
- Status: merged
- Branch: `codex/adr-0135-data-governance-mainline`
- Worktree: `.worktrees/adr-0135-mainline`
- Owner: codex
- Depends On: `adr-0094-developer-portal`, `adr-0110-platform-versioning`, `adr-0121-search-indexing-fabric`
- Conflicts With: none
- Shared Surfaces: `scripts/generate_docs_site.py`, `docs/templates/`, `docs/adr/`, `docs/runbooks/`, `tests/test_docs_site.py`, `workstreams.yaml`

## Scope

- add ADR 0135 to the repository ADR corpus
- classify generated developer-portal pages by sensitivity
- render `RESTRICTED` ADRs and runbooks as summary-only pages in the generated portal
- keep `CONFIDENTIAL` ADRs and runbooks source-only
- surface sensitivity metadata in the ADR and runbook index pages
- test metadata tagging and restricted-document rendering

## Non-Goals

- dynamic per-user role checks inside the static MkDocs site
- retroactive manual classification of every ADR and runbook in one change
- raw git repository access control

## Expected Repo Surfaces

- `docs/adr/0135-developer-portal-sensitivity-classification.md`
- `docs/workstreams/adr-0135-developer-portal-sensitivity-classification.md`
- `scripts/generate_docs_site.py`
- `docs/templates/architecture-index.md.j2`
- `docs/templates/runbooks-index.md.j2`
- `docs/runbooks/developer-portal.md`
- `tests/test_docs_site.py`

## Expected Live Surfaces

- the next docs-portal build publishes sensitivity notices on generated pages
- restricted ADRs and runbooks appear as summary-only pages in `docs.lv3.org`
- confidential ADRs and runbooks are omitted from the published portal output

## Outcome

- the docs generator now parses source-document sensitivity metadata from frontmatter or the existing top metadata block
- generated ADR, runbook, service, reference, release, and API pages now carry page-level sensitivity metadata
- ADR and runbook indexes now expose sensitivity and portal-display mode
- targeted docs-site tests now cover default tagging and restricted redaction behavior
- ADR 0135 is implemented in repository release `0.124.0`

## Verification

- run `python3 -m pytest tests/test_docs_site.py -q`
- run `python3 scripts/generate_docs_site.py --check --openapi-url ''`
- inspect generated ADR and runbook pages under `docs/site-generated/` after `make docs`

## Merge Criteria

- generated portal pages are tagged with sensitivity metadata
- restricted documents render without full body content in the published portal output
- confidential documents are omitted from portal indexes
- targeted docs-site tests pass

## Notes For The Next Assistant

- the portal currently enforces sensitivity by generated content shape, not by a separate admin-only portal runtime
- if a future role-aware portal is introduced, reuse the same metadata fields instead of inventing a second classification contract
