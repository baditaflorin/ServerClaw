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

- the pre-rebase exact-main replay remained based on fetched `origin/main`
  commit `cbf9b1ec38d4cfdb43eef6beb7b71b44f0a7b7cc` with integrated repo version
  `0.177.151` and platform version `0.130.94`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_label_studio_playbook.py tests/test_label_studio_runtime_role.py tests/test_label_studio_sync.py tests/test_generate_platform_vars.py tests/test_dependency_graph.py tests/test_edge_publication_playbooks.py tests/test_nginx_edge_publication_role.py tests/test_subdomain_catalog.py tests/test_docker_runtime_role.py tests/test_openbao_compose_env_helper.py tests/test_compose_runtime_secret_injection.py` passed with `128 passed`
- `make syntax-check-label-studio`, `make preflight WORKFLOW=converge-label-studio`, `./scripts/validate_repo.sh agent-standards workstream-surfaces health-probes`, `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, and `git diff --check` all passed before that pre-rebase exact-main live apply

## Current Branch State

- the first exact-main converge attempt failed only because
  `config/subdomain-exposure-registry.json` was stale versus the branch
  contract; that failure is preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-converge-r1.txt`
- after refreshing the exposure registry from the repo contract, `make
  converge-label-studio env=production` succeeded on `2026-04-03` across
  `postgres-lv3`, `docker-runtime-lv3`, `nginx-lv3`, and controller-local
  shared-edge verification; the successful replay is preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-mainline-converge-r2.txt`
- the successful pre-rebase replay verified the private runtime container
  health, the private version endpoint, the repo-managed project catalog
  reconciliation, the shared Typesense/API gateway dependency path, and the
  public `annotate.lv3.org` browser/API redirects through the shared auth
  boundary
- standalone public curl verification is preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0289-label-studio-public-head-r1.txt`
- `origin/main` then advanced to ADR 0299 ntfy release `0.177.152` at platform
  version `0.130.95`, so this workstream must replay the exact-main branch on
  that newer baseline before the Label Studio receipt, protected release
  surfaces, and canonical truth can be promoted safely
