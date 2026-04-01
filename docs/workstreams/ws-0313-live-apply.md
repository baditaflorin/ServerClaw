# Workstream ws-0313-live-apply: Live Apply ADR 0313 From Latest `origin/main`

- ADR: [ADR 0313](../adr/0313-contextual-help-glossary-and-escalation-drawer.md)
- Title: Ship the shared contextual help, glossary, and escalation drawer across the first-party portal surfaces
- Status: in_progress
- Branch: `codex/ws-0313-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0313-live-apply`
- Owner: codex
- Depends On: `adr-0093`, `adr-0094`, `adr-0134`, `adr-0235`, `adr-0242`, `adr-0312`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0313-live-apply.md`, `docs/adr/0313-contextual-help-glossary-and-escalation-drawer.md`, `docs/adr/.index.yaml`, `docs/runbooks/platform-operations-portal.md`, `docs/runbooks/developer-portal.md`, `docs/runbooks/deployment-history-portal.md`, `scripts/portal_utils.py`, `scripts/generate_ops_portal.py`, `scripts/generate_docs_site.py`, `scripts/generate_changelog_portal.py`, `scripts/ops_portal/`, `docs/templates/reference-index.md.j2`, `docs/templates/reference-glossary.md.j2`, `docs/theme-overrides/`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`, `tests/test_ops_portal.py`, `tests/test_interactive_ops_portal.py`, `tests/test_docs_site.py`, `tests/test_changelog_portal.py`, `tests/test_ops_portal_playbook.py`, `tests/test_ops_portal_runtime_role.py`, `receipts/live-applies/`, `receipts/live-applies/evidence/`

## Purpose

Implement ADR 0313 from the latest realistic `origin/main` baseline by adding a
shared contextual-help model that works across the repo-owned browser surfaces,
then replay the live publication paths and record enough verification evidence
for a safe exact-main merge.

## Scope

- add a reusable contextual-help and glossary model for the first-party portal
  surfaces
- wire the drawer into the interactive ops portal runtime and the generated ops
  portal snapshot
- surface the same help model in the generated docs and changelog portals
- add or refresh operational docs so operators know how to verify the new help
  affordance
- verify the relevant portal generators, runtime role checks, and live edge
  publication paths end to end

## Non-Goals

- replacing the full runbooks or ADR corpus with drawer content
- modifying third-party product-native UIs that the platform links out to
- updating protected release and canonical-truth surfaces on this workstream
  branch before the exact-main integration step

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0313-live-apply.md`
- `docs/adr/0313-contextual-help-glossary-and-escalation-drawer.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/developer-portal.md`
- `docs/runbooks/deployment-history-portal.md`
- `scripts/portal_utils.py`
- `scripts/generate_ops_portal.py`
- `scripts/generate_docs_site.py`
- `scripts/generate_changelog_portal.py`
- `scripts/ops_portal/`
- `docs/templates/reference-index.md.j2`
- `docs/templates/reference-glossary.md.j2`
- `docs/theme-overrides/`
- `docs/site-generated/architecture/dependency-graph.md`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `receipts/ops-portal-snapshot.html`
- `tests/test_ops_portal.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_docs_site.py`
- `tests/test_changelog_portal.py`
- `tests/test_ops_portal_playbook.py`
- `tests/test_ops_portal_runtime_role.py`
- `receipts/live-applies/`
- `receipts/live-applies/evidence/`

## Expected Live Surfaces

- `https://ops.lv3.org` serves the live interactive portal with the contextual
  help drawer on the root page
- `https://docs.lv3.org` serves generated docs pages with page-scoped help and
  a published glossary reference
- `https://changelog.lv3.org` serves deployment-history pages with the same
  glossary and escalation affordance
- repo-managed verification paths fail closed if the ops portal root page loses
  the help drawer contract during future replays

## Verification Plan

- run focused portal and generator tests for the ops, docs, and changelog
  surfaces
- run `make syntax-check-ops-portal`
- run `./scripts/validate_repo.sh agent-standards generated-portals`
- run the guarded ops portal live apply from this worktree
- republish the generated docs and changelog portals through the shared edge
- verify guest-local runtime HTML, generated artifact parity, and public
  unauthenticated edge redirects

## Merge-To-Main Note

This workstream intentionally defers protected surfaces such as `VERSION`,
release sections in `changelog.md`, top-level `README.md`, and
`versions/stack.yaml` until the exact-main integration step. If the branch is
fully live-applied before merge, record the evidence and receipt here so the
mainline replay can update only the protected truth surfaces that must wait.
