# ADR 0012: Proxmox Host Bridge And NAT Network

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: 0.3.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

The Proxmox host currently uses the Hetzner installimage default of assigning the public address directly to the physical NIC `enp7s0`.

That is sufficient for host access, but it does not yet provide a durable VM networking model for:

- `10.10.10.10` NGINX VM
- `10.10.10.20` Docker runtime VM
- `10.10.10.30` Docker build VM
- `10.10.10.40` monitoring VM

The initial VM set needs a predictable internal network and working outbound internet access before more advanced routing or public ingress choices are layered on top.

## Decision

We will configure the Proxmox host with two bridges:

1. `vmbr0`
   - public bridge for host management
   - carries the Hetzner public IPv4 and IPv6 configuration
   - enslaves the physical uplink `enp7s0`
2. `vmbr10`
   - private internal bridge
   - subnet: `10.10.10.0/24`
   - host bridge address: `10.10.10.1/24`

We will also enable host-side IPv4 forwarding and NAT so guests on `vmbr10` can reach the internet through the host.

## Consequences

- The host network becomes Proxmox-native instead of remaining a plain Debian routed NIC.
- Guest creation can start immediately on an internal bridge without requiring additional public IPs.
- Public ingress can later be handled deliberately at the NGINX VM or with explicit forwarding rules instead of exposing every VM directly.
- Future VLAN or routed-segment work can build on this bridge model rather than replacing it.

## Follow-up requirements

This ADR intentionally stops at bridge and outbound connectivity. Follow-up work still needs to define:

- public ingress exposure rules
- host firewall policy for forwarded traffic
- whether the build VM is reachable via VPN, bastion, or explicit port access
- backup and monitoring integration for the new guest network
