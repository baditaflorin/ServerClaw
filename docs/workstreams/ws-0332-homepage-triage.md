# Workstream ws-0332-homepage-triage: Homepage Service Failure Triage

- ADR: [ADR 0152](../adr/0152-homepage-for-unified-service-dashboard.md)
- Title: Triage failing services surfaced on `home.lv3.org` and restore safe runtime health
- Status: in_progress
- Branch: `codex/ws-0332-homepage-triage`
- Worktree: `.worktrees/ws-0332-homepage-triage`
- Owner: codex
- Depends On: `adr-0152-homepage`, `adr-0167-handoff-protocol`, `ws-0333-service-uptime-recovery`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0332-homepage-triage.md`, `playbooks/runtime-general-pool.yml`, `docs/runbooks/configure-runtime-general-pool.md`, `collections/ansible_collections/lv3/platform/roles/{docker_runtime,homepage_runtime,uptime_kuma_runtime}`, `tests/test_{docker_runtime_role,homepage_runtime_role,runtime_general_pool_playbook,uptime_kuma_runtime_role}.py`, `receipts/live-applies/`

## Purpose

Investigate the live Homepage dashboard at `home.lv3.org`, identify which
runtime-general services are degraded or failing, and restore the repo-managed
recovery path so Homepage, Uptime Kuma, and the shared edge can be replayed
safely from exact `main`.

## Observed Failure

- `https://home.lv3.org` returned an internal failure instead of the expected
  oauth2-proxy redirect chain.
- The runtime-general Traefik route for `/homepage` failed because the
  Homepage container only listened on the guest address while Traefik still
  targeted `127.0.0.1:3090`.
- The initial runtime-general replay exposed a stale Uptime Kuma runtime
  contract: the role still expected `docker-compose` and the old preflight
  variable name, while the live host needed a one-time restore of the migrated
  `kuma.db` state from `docker-runtime-lv3`.

## Planned Recovery

- bind Homepage on both the guest address and loopback so same-guest Traefik
  and verification probes keep using `127.0.0.1`
- repair the Uptime Kuma role contract to use the Docker Compose plugin and the
  real role inputs
- restore the legacy Uptime Kuma data directory onto `runtime-general-lv3`
  during the first successful runtime-general replay, then mark that migration
  complete
- keep ws-0333's fail-closed retirement guard intact while adding the new
  migration and redirect-aware verification steps

## Verification Plan

- run the focused runtime-general, Homepage, Uptime Kuma, and Docker runtime
  regression tests
- replay `runtime-general-pool` from exact `main`
- verify `home.lv3.org`, `uptime.lv3.org`, `uptime.lv3.org/dashboard`, and
  `status.lv3.org` externally after the replay
