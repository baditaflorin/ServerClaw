# ADR 0067: Guest Network Policy Enforcement

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.64.0
- Implemented In Platform Version: 0.34.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

ADR 0012 defined the bridge and NAT topology. ADR 0013 defined the public ingress model. What is missing is an explicit, enforced network policy between guests.

Currently:

- all guests can reach all other guests on `vmbr10` (10.10.10.0/24) by default
- there are no host-level or guest-level firewall rules that restrict lateral movement
- a compromised container on `docker-runtime-lv3` can freely connect to `postgres-lv3`, `backup-lv3`, or any internal service on any port
- Proxmox VE's built-in firewall is available but not configured in the repository

This is the largest remaining network-level security gap. It directly contradicts the principle of least privilege that the identity and credential ADRs enforce in the control plane.

## Decision

We will define and enforce an explicit network policy for all inter-guest and host-to-guest traffic.

Policy model:

1. **default deny** — all inter-guest traffic on `vmbr10` is blocked unless explicitly permitted
2. **explicit allow rules** are declared per VM in `inventory/host_vars/proxmox_florin.yml` under a new `network_policy:` key, mirroring the existing `guests:` structure
3. the Proxmox host role (`roles/proxmox/network/`) applies these rules to the Proxmox VE firewall (`/etc/pve/firewall/`) during convergence
4. a separate `roles/linux/guest_firewall/` role applies matching nftables rules on each guest VM for defence in depth
5. permitted flows are documented in a `docs/runbooks/network-policy-reference.md` matrix table showing which VM can reach which VM on which port

Initial permitted flows:

| Source | Destination | Port | Reason |
|---|---|---|---|
| any guest | monitoring-lv3 | 8086 (InfluxDB) | telemetry |
| docker-runtime-lv3 | postgres-lv3 | 5432 | application DB |
| docker-runtime-lv3 | step-ca (internal) | 9000 | cert renewal |
| nginx-lv3 | docker-runtime-lv3 | service ports | reverse proxy |
| any guest | host | 22 (via step-ca cert) | SSH management |
| host | any guest | 22 | Ansible convergence |

All other flows are blocked by default and must be added via a reviewed change to `proxmox_florin.yml`.

## Consequences

- Lateral movement from a compromised guest is bounded by the declared policy matrix.
- New service integrations must explicitly declare their network dependencies before they can communicate.
- The Proxmox firewall configuration becomes a managed surface that must be kept in sync with role deployments.
- Testing the policy requires a converged live environment; unit tests cannot validate actual packet filtering.

## Boundaries

- Public ingress rules (NAT forwarding to nginx) remain in ADR 0013 and are not duplicated here.
- Tailscale traffic flows are governed by Tailscale ACLs, not the Proxmox firewall.
- Inter-container traffic inside `docker-runtime-lv3` is out of scope for this ADR; container network policy is a follow-up concern.
