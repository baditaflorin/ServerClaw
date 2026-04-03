# Workstream ws-0332-homepage-triage: Homepage Service Failure Triage

- ADR: [ADR 0152](../adr/0152-homepage-for-unified-service-dashboard.md)
- Title: Triage failing Homepage services and restore safe runtime health
- Status: live_applied
- Included In Repo Version: `0.178.2`
- Canonical Mainline Receipt: `2026-04-03-ws-0332-homepage-triage-mainline-live-apply`
- Live Applied In Platform Version: `0.130.98`
- Branch: `codex/ws-0332-homepage-triage`
- Worktree: `.worktrees/ws-0332-homepage-triage`
- Owner: codex
- Depends On: `adr-0152-homepage`, `adr-0167-handoff-protocol`, `ws-0333-service-uptime-recovery`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0332-homepage-triage.md`, `playbooks/runtime-general-pool.yml`, `docs/runbooks/configure-runtime-general-pool.md`, `collections/ansible_collections/lv3/platform/roles/{docker_runtime,homepage_runtime,uptime_kuma_runtime}`, `tests/test_{docker_runtime_role,homepage_runtime_role,runtime_general_pool_playbook,uptime_kuma_runtime_role}.py`, `receipts/live-applies/`

## Scope

Investigate the live Homepage dashboard at `home.lv3.org`, identify which
runtime-general services are degraded or failing, and restore the repo-managed
recovery path so Homepage, Uptime Kuma, and the shared edge can be replayed
safely from exact `main`, then promote that replay into the protected release
and canonical-truth surfaces on the latest realistic `origin/main` baseline.

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

## Repairs Landed

- bind Homepage on both the guest address and loopback so same-guest Traefik
  and verification probes keep using `127.0.0.1`
- manage Docker guest public-edge host aliases as a repo-owned block so the
  shared runtime host recovers the expected `home.lv3.org` publication inputs
  without line-oriented drift
- repair the Uptime Kuma role contract to use the Docker Compose plugin and the
  real role inputs
- restore the legacy Uptime Kuma data directory onto `runtime-general-lv3`
  during the first successful runtime-general replay, then mark that migration
  complete
- keep ws-0333's fail-closed retirement guard intact while adding the new
  migration and redirect-aware verification steps

## Verification

- the exact-main targeted pytest slice passed with `25 passed in 27.94s` across
  `tests/test_runtime_general_pool_playbook.py`,
  `tests/test_homepage_runtime_role.py`,
  `tests/test_uptime_kuma_runtime_role.py`, and
  `tests/test_docker_runtime_role.py`, preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0332-targeted-tests-r1.txt`
- the exact-main `runtime-general-pool` replay completed successfully with
  recaps `docker-runtime-lv3 : ok=4 changed=0 failed=0`,
  `monitoring-lv3 : ok=38 changed=0 failed=0`,
  `nginx-lv3 : ok=71 changed=5 failed=0`,
  `proxmox_florin : ok=41 changed=10 failed=0`, and
  `runtime-general-lv3 : ok=322 changed=7 failed=0`, preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0332-mainline-live-apply-r1.txt`
- external verification re-confirmed the shared edge routes after the replay:
  `https://home.lv3.org` returned the expected oauth2-proxy `302`,
  `https://uptime.lv3.org` redirected to `/dashboard`,
  `https://uptime.lv3.org/dashboard` returned `200`, and
  `https://status.lv3.org` returned `200`, preserved in
  `receipts/live-applies/evidence/2026-04-03-ws-0332-public-routes-r1.txt`
- the protected release closeout on exact `main` preserved the repo-wide
  blocker status at `controller_dependency_gap x3` in
  `receipts/live-applies/evidence/2026-04-03-ws-0332-mainline-release-status-r1.json`,
  confirmed the `0.178.1 -> 0.178.2` cut in
  `receipts/live-applies/evidence/2026-04-03-ws-0332-mainline-release-dry-run-r1.txt`,
  and recorded the expected top-level release-manager refusal in
  `receipts/live-applies/evidence/2026-04-03-ws-0332-mainline-release-r1.txt`
  before the lower-level release helpers wrote the protected `0.178.2` /
  `0.130.98` truth surfaces in
  `receipts/live-applies/evidence/2026-04-03-ws-0332-mainline-release-lower-level-r1-0.178.2.txt`

## Closeout

- ws-0332 is now canonical on `main` in repository version `0.178.2`
- the corresponding exact-main live replay is recorded as platform version
  `0.130.98`
- the runtime-general replay also refreshed the governed restic receipts in
  `receipts/restic-backups/20260403T162652Z.json` and
  `receipts/restic-snapshots-latest.json`
