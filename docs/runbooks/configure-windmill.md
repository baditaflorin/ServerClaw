# Configure Windmill

## Purpose

This runbook converges the Windmill workflow runtime defined by ADR 0044.

It covers:

- PostgreSQL database and role provisioning on `postgres-lv3`
- private Windmill runtime deployment on `docker-runtime-lv3`
- a host-side mesh TCP proxy on `proxmox_florin` for operator access
- repo-managed workspace bootstrap and seeded script verification
- controller-local bootstrap secrets mirrored under `.local/windmill/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres-lv3` and `docker-runtime-lv3` are already reachable through the Proxmox jump path
3. the Proxmox host is reachable on its Headscale-managed mesh address `100.64.0.1`

## Entrypoints

- syntax check: `make syntax-check-windmill`
- preflight: `make preflight WORKFLOW=converge-windmill`
- converge: `make converge-windmill`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `windmill` on `postgres-lv3`
- PostgreSQL login role `windmill_admin` plus support role `windmill_user` on `postgres-lv3`
- Windmill runtime under `/opt/windmill` on `docker-runtime-lv3`
- private operator entrypoint at `http://100.64.0.1:8005`
- password-login bootstrap admin `superadmin_secret@windmill.dev` backed by the managed Windmill secret
- repo-managed workspace `lv3`
- seeded script `f/lv3/windmill_healthcheck`
- seeded script `f/lv3/scheduler_watchdog_loop`
- seeded script `f/lv3/rotate_credentials`
- seeded script `f/lv3/deploy_and_promote`
- seeded helper `f/lv3/mutation_audit_emit`
- seeded helper `f/lv3/lane_scheduler`
- seeded helper `f/lv3/scheduler_watchdog`
- seeded helper `f/lv3/ephemeral_vm_reaper`
- enabled schedule `f/lv3/scheduler_watchdog_loop_every_10s`
- seeded helper `f/lv3/config_merge/merge_config_changes`
- enabled schedule `f/lv3/config_merge/merge_config_changes_every_minute`
- enabled schedule `f/lv3/ephemeral_vm_reaper_every_30m`
- PostgreSQL table `config_change_staging` in the Windmill database
- enabled schedule `f/lv3/lane_scheduler_every_2s`
- enabled schedule `f/lv3/scheduler_watchdog_every_30s`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt`

## Verification

Run these checks after converge:

1. `make syntax-check-windmill`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/windmill/docker-compose.yml ps && sudo ls -l /opt/windmill/openbao /run/lv3-secrets/windmill && sudo test ! -e /opt/windmill/windmill.env'`
3. `curl -s http://100.64.0.1:8005/api/version`
4. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/users/whoami`
5. `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{"probe":"manual-run"}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fwindmill_healthcheck`
6. `curl -s -X POST http://100.64.0.1:8005/api/auth/login -H "Content-Type: application/json" -d "{\"email\":\"superadmin_secret@windmill.dev\",\"password\":\"$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)\"}"`
7. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/list | grep scheduler_watchdog_loop_every_10s`
8. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'test -s /srv/proxmox_florin_server/.local/scheduler/watchdog-heartbeat.json && sudo cat /srv/proxmox_florin_server/.local/scheduler/watchdog-heartbeat.json'`
9. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.50 "psql -d windmill -Atqc \"SELECT to_regclass('public.config_change_staging')\""`
10. `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fconfig_merge%2Fmerge_config_changes`
11. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/list | jq '.[] | select(.path=="f/lv3/lane_scheduler_every_2s" or .path=="f/lv3/scheduler_watchdog_every_30s" or .path=="f/lv3/config_merge/merge_config_changes_every_minute") | {path, enabled, schedule}'`
12. `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fephemeral_vm_reaper`
13. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/list | jq '.[] | select(.path=="f/lv3/ephemeral_vm_reaper_every_30m") | {path, enabled, schedule, script_path}'`
14. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'ls -l /srv/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json && cat /srv/proxmox_florin_server/receipts/fixtures/reaper-run-20260326T143309Z.json'`

## Notes

- Windmill stays private-only in this rollout. There is no public edge publication and no public DNS record for it.
- The current bootstrap uses a repo-managed superadmin secret mirrored locally so the repository can seed and verify the runtime without UI-only state. The same managed secret currently backs the password-login bootstrap admin for browser access. Replace that with narrower identities as ADR 0046, ADR 0047, and ADR 0056 are implemented.
- No repo-managed Windmill job in this rollout stores long-lived third-party secrets inside Windmill. Secret-bearing workflows should wait for ADR 0043 or use another approved authority.
- The seeded `f/lv3/rotate_credentials` script summarizes the canonical secret-rotation catalog and is the first Windmill surface for ADR 0065.
- The seeded `f/lv3/config_merge/merge_config_changes` worker is the ADR 0158 merge writer for `config_change_staging`.
- The ADR 0106 reaper uses the mounted worker checkout as its durable credential bridge. Keep `/srv/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json` present and `receipts/fixtures/` writable on `docker-runtime-lv3` so `run_wait_result` executions can both talk to Proxmox and persist summary receipts.
- ADR 0172 owns the live scheduler watchdog seed and schedule. ADR 0170 aligns the timeout hierarchy used around that path.
- Backup coverage comes from the existing VM backup policy: `postgres-lv3` protects the Windmill database and `docker-runtime-lv3` protects the runtime filesystem and logs.
