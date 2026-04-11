# Workstream ws-0309-live-apply: Live Apply ADR 0309 From Latest `origin/main`

- ADR: [ADR 0309](../adr/0309-task-oriented-information-architecture-across-the-platform-workbench.md)
- Title: Deliver task-oriented navigation lanes across the live ops portal, launcher, and supporting catalogs from the latest mainline baseline
- Status: live_applied
- Branch: `codex/ws-0309-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0309-live-apply`
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

## Final State

- the task-lane catalog and runtime wiring landed in the branch-local worktree,
  then the exact-main integration replay carried the result onto release
  `0.177.148`
- the canonical `ops_portal` runtime now serves the five ADR 0309 lanes
  `Start`, `Observe`, `Change`, `Learn`, and `Recover` together with the later
  ADR 0310, ADR 0312, and ADR 0313 surfaces already present on `origin/main`
- the focused portal slice passed before the mainline replay:
  `53` targeted tests, `python3 -m py_compile` for the affected Python entry
  points, `scripts/validate_repository_data_models.py --validate`,
  `scripts/generate_ops_portal.py --check`, `make syntax-check-ops-portal`,
  and the owned `validate_repo.sh` gates

## Branch-Local Replay Status

- the first isolated-worktree replay is still preserved in
  `receipts/live-applies/evidence/2026-04-02-ws-0309-branch-live-apply.txt`
- that branch-local run failed closed at canonical-truth refresh because the
  protected top-level `README.md` summary had to be regenerated from the final
  integration branch instead of from the workstream branch
- no branch-local integration-only surfaces remain; the exact-main replay,
  release cut, and live verification completed in
  `codex/ws-0309-main-integration`

## Verification Outcome

- guest-local verification on `docker-runtime` confirmed
  `{"status":"ok"}`, the task-lane/help markers, the deployed
  `workbench_information_architecture.py` helper, the synced
  `workbench-information-architecture.json` catalog, and a healthy
  `ops-portal` container
- internal edge publication still returns the expected `302` to
  `https://ops.example.com/oauth2/sign_in?...` for unauthenticated requests
- the post-apply restic trigger initially failed because the local OpenBao API
  was sealed; a narrow repo-managed unseal replay recovered that state and the
  follow-on backup succeeded with receipt `receipts/restic-backups/20260403T001854Z.json`

## Merge Notes

- merged through the exact-main integration branch on repository version
  `0.177.148`
- first verified live on platform version `0.130.93`
- a later `origin/main` sync added repo-local operator tooling at
  `ef412b0f061517b64920b7328102e23b89b0774d`; that closeout sync does not
  change the already-live `ops_portal` runtime payload for ADR 0309
