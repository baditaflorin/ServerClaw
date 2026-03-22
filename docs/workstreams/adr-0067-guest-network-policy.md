# Workstream ADR 0067: Guest Network Policy Enforcement

- ADR: [ADR 0067](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0067-guest-network-policy-enforcement.md)
- Title: Explicit default-deny network policy between guests with managed allow rules
- Status: live_applied
- Branch: `codex/adr-0067-guest-network-policy`
- Worktree: `../proxmox_florin_server-guest-network-policy`
- Owner: codex
- Depends On: `adr-0012-proxmox-host-bridge-and-nat-network`, `adr-0013-public-ingress`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox_florin.yml`, Proxmox VE firewall, `roles/proxmox/network/`, `roles/linux/`

## Scope

- add `network_policy:` key to `inventory/host_vars/proxmox_florin.yml` with the initial allow matrix
- extend `roles/proxmox/network/` to apply Proxmox VE firewall rules from `network_policy`
- create `roles/linux/guest_firewall/` role for nftables defence-in-depth rules on each guest
- write `docs/runbooks/network-policy-reference.md` matrix table
- add `make validate` check that `network_policy` is present and parseable

## Non-Goals

- container-level network policies inside `docker-runtime-lv3`
- Tailscale ACL management

## Expected Repo Surfaces

- updated `inventory/host_vars/proxmox_florin.yml`
- updated `roles/proxmox/network/tasks/firewall.yml`
- `roles/linux/guest_firewall/` role
- `docs/runbooks/network-policy-reference.md`
- `docs/adr/0067-guest-network-policy-enforcement.md`
- `docs/workstreams/adr-0067-guest-network-policy.md`
- `workstreams.yaml`

## Expected Live Surfaces

- Proxmox VE firewall enabled with default-deny inter-guest policy
- nftables rules active on each guest VM
- traffic matrix matches the documented allow list

## Verification

- `make converge-guest-network-policy`
- `ansible -i inventory/hosts.yml docker-runtime-lv3 -m shell -a 'timeout 3 bash -lc "exec 3<>/dev/tcp/10.10.10.50/5432 && echo allowed && exec 3<&- && exec 3>&-"' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `ansible -i inventory/hosts.yml nginx-lv3 -m shell -a 'timeout 3 bash -lc "exec 3<>/dev/tcp/10.10.10.20/3001 && echo allowed && exec 3<&- && exec 3>&-"' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `ansible -i inventory/hosts.yml docker-build-lv3 -m shell -a 'timeout 3 bash -lc "exec 3<>/dev/tcp/10.10.10.40/3100 && echo allowed && exec 3<&- && exec 3>&-"' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- `ansible -i inventory/hosts.yml backup-lv3 -m shell -a 'timeout 3 bash -lc "exec 3<>/dev/tcp/10.10.10.50/5432 && echo unexpected-open && exec 3<&- && exec 3>&-"' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump` should fail with `rc=124`
- `ansible -i inventory/hosts.yml postgres-lv3 -m shell -a 'timeout 3 bash -lc "exec 3<>/dev/tcp/10.10.10.20/8082 && echo unexpected-open && exec 3<&- && exec 3>&-"' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump` should fail with `rc=124`

## Merge Criteria

- the network-policy reference matrix is complete for all current guests
- the default-deny rule does not block the Ansible management SSH path
- a receipt documents the first successful converge with the policy active

## Notes For The Next Assistant

- apply the Proxmox host firewall change before the guest nftables rules; the host firewall is the outer enforcement point
- test Ansible SSH reachability to all guests immediately after enabling default-deny to avoid a lockout
- this workstream is merged to `main` and applied live
