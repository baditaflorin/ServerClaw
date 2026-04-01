# Workstream ws-0289-label-studio-live-apply: ADR 0289 Label Studio Live Apply

- ADR: [ADR 0289](../adr/0289-label-studio-as-the-human-in-the-loop-data-annotation-platform.md)
- Title: deploy Label Studio from the latest realistic `origin/main` baseline without colliding with the existing Directus `ws-0289-*` records
- Status: in_progress
- Included In Repo Version: not yet
- Canonical Mainline Receipt: not yet
- Live Applied In Platform Version: not yet
- Branch: `codex/ws-0289-label-studio-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0289-label-studio-live-apply-r1`
- Owner: codex
- Depends On: none
- Conflicts With: `ws-0289-live-apply`

## Naming Note

`origin/main` already contains `ws-0289-live-apply` for the Directus ADR that
shares the same numeric identifier. This collision-safe Label Studio record
keeps the annotation-platform delivery merge-safe by using an explicit
`ws-0289-label-studio-*` namespace for the ADR-local state.

## Scope

- add the repo-managed Label Studio PostgreSQL and runtime roles, playbooks,
  project catalog sync helper, and verification tasks
- carry the private runtime, public edge publication, health probes, SLOs,
  workflow metadata, and service-catalog truth onto the latest realistic
  `origin/main` baseline
- pin the reviewed `docker.io/heartexlabs/label-studio:1.23.0` runtime image
  by digest and record the Trivy scan receipt
- record the branch-local and exact-main live-apply evidence separately so the
  protected release and canonical truth surfaces can be updated only after the
  mainline replay is verified

## Current Branch State

- latest fetched `origin/main` is commit `cbf9b1ec3` (`[live-apply] Finalize ADR 0275 exact-main Tika replay`)
  with integrated repo version `0.177.151` and platform version `0.130.94`
- exact-main integration kept the current Superset runtime on `8105`, so
  Label Studio now uses `8110` throughout the private runtime, firewall,
  health, SLO, and workflow contracts on the latest realistic `origin/main`
- browser access is enforced at the shared edge through oauth2-proxy and
  Keycloak, while Label Studio's admin password and token remain the
  Community Edition-compatible automation and recovery path
- the reviewed runtime image is
  `docker.io/heartexlabs/label-studio:1.23.0@sha256:aa461572e8f9d86a1bf9520c1db620204e86160fd2f80dd7e9d40ac84a8828ea`
  with Trivy summary `0 critical / 11 high`

## Validation Status

- the rebased branch replays cleanly on top of the latest fetched `origin/main`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_label_studio_playbook.py tests/test_label_studio_runtime_role.py tests/test_label_studio_sync.py tests/test_generate_platform_vars.py tests/test_dependency_graph.py tests/test_edge_publication_playbooks.py tests/test_nginx_edge_publication_role.py tests/test_subdomain_catalog.py` passed with `86 passed`
- `make syntax-check-label-studio`, `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, `./scripts/validate_repo.sh agent-standards workstream-surfaces health-probes`, `git diff --check`, and `make preflight WORKFLOW=converge-label-studio` all passed on `2026-04-01`
- `make pre-push-gate` exercised the full remote and local fallback automation path on `2026-04-01`; every selected lane passed except `generated-docs`, which failed only because `README.md` canonical truth is intentionally deferred on this workstream branch until exact-main integration
- a branch push attempt hit the same expected `generated-docs` / `README.md` canonical-truth gate, so the branch remains local until the final mainline integration step updates the protected canonical truth surfaces

## Current Blocker

- live apply is blocked by active exclusive ADR 0153 locks held by
  `agent:codex/ws-0293-live-apply-r2` on `host:proxmox_florin`, `vm:110`, and
  `vm:120`; their expiry continued to heartbeat forward through at least
  `2026-04-01T15:06:11Z`
- wait-acquire sessions are already queued for `host:proxmox_florin`,
  `vm:110`, and `vm:120` under
  `agent:codex/ws-0289-label-studio-live-apply-r1` so this workstream can
  start the live converge immediately after the current holder releases them

## Remaining For Main Integration

- finish the focused repository validation and branch-local live apply
- capture the branch-local receipt and evidence bundle
- replay the change onto exact `main`, then update `README.md`, `VERSION`,
  `changelog.md`, `versions/stack.yaml`, and any generated canonical truth
  files only after the mainline verification passes
