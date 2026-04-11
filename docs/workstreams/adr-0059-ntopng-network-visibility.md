# Workstream ADR 0059: ntopng For Private Network Flow Visibility

- ADR: [ADR 0059](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0059-ntopng-for-private-network-flow-visibility.md)
- Title: Visual network-flow analysis for the private guest network
- Status: live_applied
- Branch: `codex/adr-0059-ntopng`
- Worktree: `../proxmox-host_server-ntopng`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0012-proxmox-host-bridge-and-nat-network`, `adr-0049-private-api-publication`
- Conflicts With: none
- Shared Surfaces: `vmbr10`, ingress traffic, guest egress, network triage

## Scope

- choose ntopng for network-flow visibility
- define safe collection points and operator access boundaries
- improve triage for private-network incidents and anomalies

## Non-Goals

- packet capture by default
- turning observability tooling into inline network enforcement

## Expected Repo Surfaces

- `docs/adr/0059-ntopng-for-private-network-flow-visibility.md`
- `docs/runbooks/configure-ntopng.md`
- `docs/workstreams/adr-0059-ntopng-network-visibility.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `playbooks/ntopng.yml`
- `roles/proxmox_ntopng/`
- `inventory/group_vars/all.yml`
- `inventory/host_vars/proxmox-host.yml`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `workstreams.yaml`

## Expected Live Surfaces

- host-local ntopng capture on `vmbr10` and `vmbr0`
- operator-only network-flow visibility at `http://100.118.189.95:3001`
- recent-history views for incident and capacity analysis

## Verification

- `make syntax-check-ntopng`
- `make converge-ntopng`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo systemctl is-active redis-server ntopng'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'PASS=$(sudo cat /etc/lv3/ntopng/admin-password); curl -fsS -u admin:${PASS} http://100.118.189.95:3001/lua/rest/v2/get/ntopng/interfaces.lua'`

## Merge Criteria

- the repo has a dedicated ntopng converge path with operator-only publication and host-side collection boundaries
- the live host exposes ntopng only through the documented Tailscale path
- interface discovery and private-network host visibility verify through the managed API surface
- a live-apply receipt is recorded before final push

## Notes For The Next Assistant

- Live apply completed on `2026-03-22` through `make converge-ntopng` from `main`.
- The first implementation stays on the Proxmox host because `ntopng` itself is not a NetFlow collector and `vmbr10` visibility matters more than central placement.
- The operator-facing path is the host Tailscale proxy on port `3001`; there is no public DNS or edge publication for ntopng.
