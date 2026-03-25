# Workstream ADR 0144: Headscale Mesh Control Plane

- ADR: [ADR 0144](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-headscale/docs/adr/0144-headscale-for-zero-trust-mesh-vpn.md)
- Title: Replace the hosted mesh control plane with repo-managed Headscale while preserving Tailscale client access and the `10.10.10.0/24` subnet route
- Status: implemented
- Branch: `codex/adr-0144-headscale`
- Worktree: `../proxmox_florin_server-headscale`
- Owner: codex
- Depends On: `adr-0014-tailscale`
- Conflicts With: work that assumes the commercial Tailscale tailnet IPs or operator-enrollment API remain canonical
- Shared Surfaces: `inventory/hosts.yml`, `inventory/host_vars/proxmox_florin.yml`, `config/service-capability-catalog.json`, `config/control-plane-lanes.json`, `README.md`, `versions/stack.yaml`

## Scope

- deploy Headscale on `proxmox_florin`
- publish `headscale.lv3.org` through the existing NGINX edge VM
- store Headscale ACLs and route approvers in repo-managed policy
- add a dedicated Headscale converge playbook, workflow, and command contract
- migrate the Proxmox host and one operator workstation to the Headscale control plane
- verify host access, the `10.10.10.0/24` subnet route, and operator ACL coverage
- update repo truth to the new management mesh IP and mark ADR 0144 implemented

## Non-Goals

- replacing the Tailscale client binary on managed hosts or operator devices
- deploying a custom DERP region in this phase
- fully redesigning ADR 0108 operator onboarding and offboarding around Headscale APIs in the same cut

## Expected Repo Surfaces

- `collections/ansible_collections/lv3/platform/roles/proxmox_headscale/`
- `playbooks/headscale.yml`
- `playbooks/services/headscale.yml`
- `config/headscale-acl.hujson`
- `docs/adr/0144-headscale-for-zero-trust-mesh-vpn.md`
- `docs/runbooks/configure-headscale.md`
- `docs/workstreams/adr-0144-headscale.md`
- catalog and status updates for the new `headscale` service

## Expected Live Surfaces

- Headscale systemd service on `proxmox_florin`
- `https://headscale.lv3.org`
- Proxmox host enrolled in Headscale as the `ops@`-owned node `proxmox-florin-subnet-router`
- `10.10.10.0/24` advertised and reachable through the Proxmox host route
- operator workstation enrolled in the same Headscale-managed mesh

## Verification

- `make syntax-check-headscale`
- `make converge-headscale`
- `curl -I https://headscale.lv3.org/health`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 sudo headscale --config /etc/headscale/config.yaml nodes list`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@10.10.10.30 hostname`

## Merge Criteria

- the Headscale control plane is converged from repo automation
- the public hostname proxies cleanly through the shared edge
- the Proxmox host and operator workstation are both migrated successfully
- the guest subnet route and operator ACL path are verified
- the repo truth reflects the new management mesh IP and live receipt

## Notes

- Headscale 0.28.0 did not auto-promote the advertised subnet route into `approved_routes` during the first live cutover, so the role now reconciles route approval after the host node exists.
