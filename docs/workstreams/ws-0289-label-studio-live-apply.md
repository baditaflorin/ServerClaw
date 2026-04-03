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

- exact-main integration kept the current Superset runtime on `8105`, so
  Label Studio now uses `8110` throughout the private runtime, firewall,
  health, SLO, and workflow contracts on the latest realistic `origin/main`
- browser access is enforced at the shared edge through oauth2-proxy and
  Keycloak, while Label Studio's admin password and token remain the
  Community Edition-compatible automation and recovery path
- the reviewed runtime image is
  `docker.io/heartexlabs/label-studio:1.23.0@sha256:aa461572e8f9d86a1bf9520c1db620204e86160fd2f80dd7e9d40ac84a8828ea`
  with Trivy summary `0 critical / 11 high`

## Remaining For Main Integration

- finish the focused repository validation and branch-local live apply
- capture the branch-local receipt and evidence bundle
- replay the change onto exact `main`, then update `README.md`, `VERSION`,
  `changelog.md`, `versions/stack.yaml`, and any generated canonical truth
  files only after the mainline verification passes
