# Configure NetBox

## Purpose

This runbook converges the NetBox inventory and IPAM plane defined by ADR 0054.

It covers:

- PostgreSQL database and role provisioning on `postgres-lv3`
- private NetBox runtime deployment on `docker-runtime-lv3`
- a host-side Tailscale TCP proxy on `proxmox_florin` for operator and agent access
- repo-managed synchronization of the canonical host, VM, network, and governed service inventory into NetBox
- controller-local bootstrap secrets mirrored under `.local/netbox/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres-lv3` and `docker-runtime-lv3` are already reachable through the Proxmox jump path
3. the Proxmox host is reachable on its Tailscale address `100.118.189.95`

## Entrypoints

- syntax check: `make syntax-check-netbox`
- preflight: `make preflight WORKFLOW=converge-netbox`
- converge: `make converge-netbox`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `netbox` on `postgres-lv3`
- NetBox runtime under `/opt/netbox` on `docker-runtime-lv3`
- Tailscale-only operator and agent entrypoint at `http://100.118.189.95:8004`
- repo-managed NetBox site, device, VM, prefix, IP, and governed-service inventory synchronized from canonical repository state

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/netbox/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/netbox/superuser-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/netbox/api-token.txt`

## Verification

Run these checks after converge:

1. `make syntax-check-netbox`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/netbox/docker-compose.yml ps && sudo ls -l /opt/netbox/openbao /run/lv3-secrets/netbox && sudo test ! -e /opt/netbox/netbox.env'`
3. `curl -s -o /dev/null -w '%{http_code}\n' http://100.118.189.95:8004/login/`
4. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/netbox/api-token.txt)" http://100.118.189.95:8004/api/virtualization/virtual-machines/?limit=20`
5. `uvx --from pyyaml python /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/netbox_inventory_sync.py --api-url http://100.118.189.95:8004 --api-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/netbox/api-token.txt --host-vars /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml --stack /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml --lane-catalog /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json`

## Notes

- NetBox stays private-only in this rollout. There is no public DNS record and no public edge publication.
- The repository remains the source of truth. The NetBox sync is deliberately one-way from canonical repo data into the NetBox API.
- The synchronized inventory now includes the Hetzner site, the Proxmox host, all six managed VMs, both canonical prefixes, their primary IP assignments, and the governed service catalog derived from repo topology plus published/private control-plane lanes.
- The bootstrap superuser and API token are enough for repo-managed synchronization today. ADR 0056 should replace this with brokered identity once Keycloak is live.
- Backup coverage currently comes from the existing VM backup policy: `postgres-lv3` protects the NetBox database and `docker-runtime-lv3` protects the runtime filesystem and Redis state.
