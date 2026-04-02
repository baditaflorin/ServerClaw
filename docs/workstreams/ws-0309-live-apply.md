# Workstream ws-0309-live-apply: Live Apply ADR 0309 From Latest `origin/main`

- ADR: [ADR 0309](../adr/0309-task-oriented-information-architecture-across-the-platform-workbench.md)
- Title: Deliver task-oriented navigation lanes across the live ops portal, launcher, and supporting catalogs from the latest mainline baseline
- Status: in_progress
- Branch: `codex/ws-0309-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0309-live-apply`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0152-homepage-for-unified-service-dashboard`, `adr-0234-shared-human-app-shell-and-navigation-via-patternfly`, `adr-0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher`, `adr-0239-browser-local-search-experience-via-pagefind`, `adr-0313-contextual-help-glossary-and-escalation-drawer`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0309-live-apply.md`, `docs/adr/0309-task-oriented-information-architecture-across-the-platform-workbench.md`, `docs/adr/.index.yaml`, `docs/runbooks/platform-operations-portal.md`, `config/persona-catalog.json`, `config/workflow-catalog.json`, `config/workbench-information-architecture.json`, `docs/schema/persona-catalog.schema.json`, `docs/schema/workbench-information-architecture.schema.json`, `scripts/workbench_information_architecture.py`, `scripts/workflow_catalog.py`, `scripts/validate_repository_data_models.py`, `scripts/ops_portal/`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/`, `tests/test_interactive_ops_portal.py`, `tests/test_ops_portal.py`, `tests/test_ops_portal_runtime_role.py`, `receipts/live-applies/*adr-0309*`, `receipts/live-applies/evidence/*ws-0309*`

## Purpose

Implement ADR 0309 by adding a canonical task-lane catalog and then making the
live interactive ops portal navigate by `Start`, `Observe`, `Change`, `Learn`,
and `Recover` instead of relying on product-first launcher taxonomy alone.

## Scope

- add a machine-readable task-lane overlay above the service, workflow, and
  runbook catalogs
- teach the interactive ops portal shell, launcher, and section metadata to
  render and route through those lanes
- sync the new catalog into the live `ops_portal` runtime and validate the
  repo and runtime contracts end to end
- record branch-local live-apply evidence and then carry the verified result
  onto `main`

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0309-live-apply.md`
- `docs/adr/0309-task-oriented-information-architecture-across-the-platform-workbench.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/platform-operations-portal.md`
- `config/persona-catalog.json`
- `config/workflow-catalog.json`
- `config/workbench-information-architecture.json`
- `docs/schema/persona-catalog.schema.json`
- `docs/schema/workbench-information-architecture.schema.json`
- `scripts/workbench_information_architecture.py`
- `scripts/workflow_catalog.py`
- `scripts/validate_repository_data_models.py`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/static/portal.css`
- `scripts/ops_portal/static/portal.js`
- `scripts/ops_portal/templates/base.html`
- `scripts/ops_portal/templates/index.html`
- `scripts/ops_portal/templates/macros/lane_context.html`
- `scripts/ops_portal/templates/partials/launcher.html`
- `scripts/ops_portal/templates/partials/runbooks.html`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/verify.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `receipts/live-applies/*adr-0309*`
- `receipts/live-applies/evidence/*ws-0309*`

## Current Progress

- branch-local implementation is in progress in the isolated worktree created
  from the former `origin/main` commit `cbb0c99f3f69c3ab2bb7658daf443c45df9ea49b`
- the current branch already includes a new
  `config/workbench-information-architecture.json` overlay, schema support, and
  portal runtime changes that start mapping services, workflows, runbooks, and
  pages onto task lanes
- after the workstream started, `origin/main` advanced to
  `5f93f0cf809ffcc755a41be2678e76350933ed37`, including overlapping
  `ops_portal` changes from later ADRs, so the next critical step is to refresh
  this workstream onto that newer mainline before final validation and live
  apply
- the workstream has now been rebased onto `5f93f0cf809ffcc755a41be2678e76350933ed37`,
  and the latest-main branch tree passes:
  `33` focused portal tests, `python3 scripts/validate_repository_data_models.py --validate`,
  `python3 scripts/generate_ops_portal.py --check`, `make syntax-check-ops-portal`,
  and `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-portals`

## Branch-Local Replay Status

- the first isolated-worktree production replay attempt is preserved in
  `receipts/live-applies/evidence/2026-04-02-ws-0309-branch-live-apply.txt`
- preflight succeeded and regenerated the required portal artifacts, but the
  governed wrapper then stopped at `make check-canonical-truth` because
  `workstreams.yaml` changed and the generated top-level `README.md` summary was
  therefore stale
- per the workstream rules, that README refresh is an integration-only surface
  and should land only in the final exact-main step, so the actual production
  replay continues in the dedicated latest-main integration worktree rather than
  by force-writing protected truth onto this branch

## Verification Plan

- run focused portal and role tests after the latest-main refresh
- run the repository data-model and portal generation checks
- perform the governed `ops_portal` live apply from this worktree
- verify the live root page and partials on `docker-runtime-lv3`
- record the branch-local receipt and evidence bundle
- replay the exact integrated result from `main`, then update ADR metadata with
  the first repo/platform versions where implementation is true

## Merge Notes

- do not bump `VERSION`, update numbered release sections in `changelog.md`,
  edit the top-level README integrated status summary, or change
  `versions/stack.yaml` while this remains the workstream branch
- if the branch completes the live apply before the protected mainline refresh,
  keep the branch-local receipt and evidence here and state explicitly which
  integration-only files remain for the final `main` step
