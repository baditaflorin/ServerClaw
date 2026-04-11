# Workstream ADR 0054: NetBox For Topology, IPAM, And Inventory

- ADR: [ADR 0054](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0054-netbox-for-topology-ipam-and-inventory.md)
- Title: Visual infrastructure inventory and IPAM plane
- Status: live_applied
- Branch: `codex/adr-0054-netbox-topology`
- Worktree: `../proxmox-host_server-netbox-topology`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: topology catalog, VM inventory, IP addressing, ownership metadata

## Scope

- choose NetBox for visual topology and IPAM
- define repo-sync and ownership boundaries
- expose structured infrastructure metadata for humans and agents

## Non-Goals

- turning NetBox into an unsupervised mutation surface
- replacing canonical repo documents with free-form UI edits

## Expected Repo Surfaces

- `docs/adr/0054-netbox-for-topology-ipam-and-inventory.md`
- `docs/workstreams/adr-0054-netbox-topology.md`
- `docs/runbooks/configure-netbox.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `playbooks/netbox.yml`
- `roles/netbox_postgres/`
- `roles/netbox_runtime/`
- `roles/netbox_sync/`
- `scripts/netbox_inventory_sync.py`
- `workstreams.yaml`

## Expected Live Surfaces

- private NetBox runtime on `docker-runtime`
- PostgreSQL database `netbox` on `postgres`
- Tailscale operator and agent entrypoint at `http://100.118.189.95:8004`
- synchronized site, host, VM, prefix, IP, and governed service inventory views

## Verification

- `make syntax-check-netbox`
- `make converge-netbox`
- `curl -s -o /dev/null -w '%{http_code}\n' http://100.118.189.95:8004/login/`
- `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/netbox/api-token.txt)" http://100.118.189.95:8004/api/virtualization/virtual-machines/?limit=20`
- `uvx --from pyyaml python /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/netbox_inventory_sync.py --api-url http://100.118.189.95:8004 --api-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/netbox/api-token.txt --host-vars /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/host_vars/proxmox-host.yml --stack /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/versions/stack.yaml --lane-catalog /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/control-plane-lanes.json`

## Merge Criteria

- the repo-managed NetBox converge path applies cleanly from `main`
- the private API, synchronized topology inventory, and idempotent re-sync path are verified live

## Notes For The Next Assistant

- keep repo-to-NetBox synchronization narrower than full bidirectional sync at first
- prefer importing new inventory classes from canonical repo metadata before allowing direct UI-side edits
