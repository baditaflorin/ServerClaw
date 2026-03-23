# Configure Windmill

## Purpose

This runbook converges the Windmill workflow runtime defined by ADR 0044.

It covers:

- PostgreSQL database and role provisioning on `postgres-lv3`
- private Windmill runtime deployment on `docker-runtime-lv3`
- a host-side Tailscale TCP proxy on `proxmox_florin` for operator access
- repo-managed workspace bootstrap and seeded script verification
- controller-local bootstrap secrets mirrored under `.local/windmill/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres-lv3` and `docker-runtime-lv3` are already reachable through the Proxmox jump path
3. the Proxmox host is reachable on its Tailscale address `100.118.189.95`

## Entrypoints

- syntax check: `make syntax-check-windmill`
- preflight: `make preflight WORKFLOW=converge-windmill`
- converge: `make converge-windmill`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `windmill` on `postgres-lv3`
- PostgreSQL login role `windmill_admin` plus support role `windmill_user` on `postgres-lv3`
- Windmill runtime under `/opt/windmill` on `docker-runtime-lv3`
- Tailscale-only operator entrypoint at `http://100.118.189.95:8005`
- repo-managed workspace `lv3`
- seeded script `f/lv3/windmill_healthcheck`
- seeded script `f/lv3/rotate_credentials`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt`

## Verification

Run these checks after converge:

1. `make syntax-check-windmill`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --env-file /opt/windmill/windmill.env --file /opt/windmill/docker-compose.yml ps'`
3. `curl -s http://100.118.189.95:8005/api/version`
4. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.118.189.95:8005/api/users/whoami`
5. `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{"probe":"manual-run"}' http://100.118.189.95:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fwindmill_healthcheck`

## Notes

- Windmill stays private-only in this rollout. There is no public edge publication and no public DNS record for it.
- The current bootstrap uses a repo-managed superadmin secret mirrored locally so the repository can seed and verify the runtime without UI-only state. Replace that with narrower identities as ADR 0046, ADR 0047, and ADR 0056 are implemented.
- No repo-managed Windmill job in this rollout stores long-lived third-party secrets inside Windmill. Secret-bearing workflows should wait for ADR 0043 or use another approved authority.
- The seeded `f/lv3/rotate_credentials` script summarizes the canonical secret-rotation catalog and is the first Windmill surface for ADR 0065.
- Backup coverage comes from the existing VM backup policy: `postgres-lv3` protects the Windmill database and `docker-runtime-lv3` protects the runtime filesystem and logs.
