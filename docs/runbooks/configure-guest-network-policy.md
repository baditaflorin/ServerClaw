# Configure Guest Network Policy

## Purpose

This runbook converges ADR 0067 by enforcing the canonical guest network policy on both layers that matter:

- Proxmox VM firewalls on the host
- guest-local `nftables` policy on every managed VM

## Entrypoints

- syntax check: `make syntax-check-guest-network-policy`
- preflight: `make preflight WORKFLOW=converge-guest-network-policy`
- converge: `make converge-guest-network-policy`

## Preconditions

1. The controller SSH key exists at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`.
2. The Proxmox host is reachable at `100.118.189.95`.
3. Every managed guest is reachable through the Proxmox jump path.
4. The canonical allow matrix in `inventory/host_vars/proxmox_florin.yml` has been reviewed before apply.

## What The Workflow Changes

1. Renders one Proxmox firewall file per managed VM under `/etc/pve/firewall/<vmid>.fw`.
2. Enables `firewall=1` on each VM `net0` interface without rewriting unrelated VM hardware settings.
3. Maintains the Proxmox host conntrack-zone helper needed for `fwbr+` bridge traffic to preserve NATed guest egress after VM firewalls are enabled.
4. Compiles and restarts `pve-firewall` on the Proxmox host when the per-VM policy changes.
5. Renders `/etc/nftables.conf` on each guest from the same canonical `network_policy` data for both local services and Docker-published forwards.
6. Reloads guest `nftables` and verifies that SSH reconnects cleanly after the policy change.

## Canonical Policy Source

- policy source: [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)
- flow reference: [docs/runbooks/network-policy-reference.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/network-policy-reference.md)
- playbook: [playbooks/guest-network-policy.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/guest-network-policy.yml)

## Verification

Run these checks after converge:

1. `make syntax-check-guest-network-policy`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pve-firewall compile >/dev/null && sudo ls /etc/pve/firewall/*.fw'`
3. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'nc -z -w 2 10.10.10.50 5432'`
4. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.50 'nc -z -w 2 10.10.10.20 8080'`

## Notes

- The workflow is intentionally host-first, then guest-side, so the outer firewall layer is active before guest-local defence in depth.
- Unlisted inter-guest flows are denied by default.
- Public ingress and host-side Tailscale proxy paths remain governed by the same host inventory and must be kept in the allow matrix.
