# Workstream ws-0260-live-apply: ADR 0260 Live Apply From Latest `origin/main`

- ADR: [ADR 0260](../adr/0260-nextcloud-as-the-canonical-personal-data-plane-for-serverclaw.md)
- Title: Nextcloud personal data plane live apply from latest `origin/main`
- Status: `live_applied`
- Branch: `codex/ws-0260-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0260-live-apply`
- Owner: codex
- Included In Repo Version: 0.177.91
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0260-nextcloud-personal-data-plane-mainline-live-apply.json`
- Depends On: `adr-0206-ports-and-adapters-for-external-integrations`, `adr-0259-n8n-as-the-external-app-connector-fabric-for-serverclaw`
- Conflicts With: none

## Purpose

Implement ADR 0260 by making Nextcloud the repo-managed personal data plane on
`docker-runtime-lv3`, publishing `cloud.lv3.org` through the shared NGINX edge,
and preserving enough branch-local state that a later exact-main replay can
promote the service onto the protected `main` surfaces safely.

## Branch-Local Delivery

- `d10f8e008` added the repo-managed Nextcloud runtime, PostgreSQL backend,
  edge publication, health probes, catalogs, and image-scan evidence.
- `f796d47fd` hardened the earlier replay path.
- `30d8109d8` and `bb26d6658` made the runtime recover stale compose networks
  and missing Docker bridge chains instead of requiring manual Docker cleanup.
- `fa3314228` and `fa41c419f` extended the shared OpenBao compose-env helper so
  downstream consumers like Nextcloud can recover a detached local
  `lv3-openbao` publication before runtime secret injection.

## Verification

- The first synchronized mainline proof on 2026-03-29 is preserved in
  `receipts/live-applies/2026-03-29-adr-0260-nextcloud-personal-data-plane-mainline-live-apply.json`,
  but it became non-canonical once `origin/main` advanced to release `0.177.90`.
- The authoritative exact-main replay moved to release `0.177.91` from
  integration source commit `9db57048717121e6a0d933d44e87ac3835551baf` after
  refreshing this work onto `origin/main` commit
  `f965aa3101fa2cd2260a8e6fda165f366365ed80`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=nextcloud env=production`
  completed successfully on that synchronized tree with final recap
  `docker-runtime-lv3 ok=156 changed=4 failed=0 skipped=32`,
  `nginx-lv3 ok=38 changed=4 failed=0 skipped=7`,
  `postgres-lv3 ok=52 changed=0 failed=0 skipped=14`, and
  `localhost ok=18 changed=0 failed=0 skipped=3`.
- Public verification after the replay returned `installed=true` from
  `https://cloud.lv3.org/status.php`, and both `/.well-known/caldav` plus
  `/.well-known/carddav` returned `HTTP/2 301` with
  `location: https://cloud.lv3.org/remote.php/dav/`.
- Guest-local verification through the managed Proxmox jump path returned the
  same `status.php` payload from `http://10.10.10.20:8084/status.php`, kept
  `backgroundjobs_mode=cron`, confirmed `ops` as the enabled admin user, and
  showed the published `0.0.0.0:8084->80/tcp` listener on `nextcloud-app`.
- Follow-up container-health inspection confirmed both `nextcloud-redis` and
  `nextcloud-openbao-agent` reached `Status: healthy` after the replay.

## Outcome

- ADR 0260 is now implemented on integrated repo version `0.177.91` and live
  platform version `0.130.61`.
- `receipts/live-applies/2026-03-30-adr-0260-nextcloud-personal-data-plane-mainline-live-apply.json`
  supersedes the earlier 2026-03-29 mainline receipt as the canonical proof
  for `nextcloud`.
