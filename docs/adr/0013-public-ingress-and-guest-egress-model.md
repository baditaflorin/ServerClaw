# ADR 0013: Public Ingress And Guest Egress Model

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.12.0
- Implemented In Platform Version: 0.9.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

ADR 0012 established the Proxmox bridge model:

- `vmbr0` as the public bridge
- `vmbr10` as the internal `10.10.10.0/24` bridge
- host-side NAT for guest egress

That solves raw connectivity, but it does not yet define which guests are reachable from the public internet and how ingress should flow through the platform.

The initial VM set has different exposure requirements:

- `10.10.10.10` NGINX VM should act as the public edge
- `10.10.10.20` Docker runtime VM should not be public by default
- `10.10.10.30` Docker build VM should not be public by default
- `10.10.10.40` monitoring VM should not be public by default

## Decision

We will use a single-edge ingress model in phase one.

Egress:

- all VMs on `10.10.10.0/24` use `10.10.10.1` as their default gateway
- outbound internet access is provided by host-side NAT on the Proxmox node

Ingress:

- the public internet reaches only the NGINX VM as the intended edge workload
- public HTTP and HTTPS traffic on the host public IP should be forwarded to `10.10.10.10`
- other private VMs remain non-public unless an explicit ADR authorizes a public exposure path

## Consequences

- The NGINX VM becomes the stable ingress point for external traffic.
- Runtime, build, and monitoring workloads remain private by default.
- TLS termination, routing, and public service publishing are centralized instead of being scattered across guests.
- Public exposure decisions become explicit because new public services require either NGINX routing or a new ADR.

## Implementation Note

This ADR is implemented through host-side nftables DNAT on the public Proxmox node:

- TCP `80` and `443` on the public host IPv4 are forwarded to `10.10.10.10`
- only the declared edge VM receives public ingress by default
- guest egress remains host-side NAT through `10.10.10.1`

TLS certificate handling and internal naming for upstream applications remain follow-on concerns, but they do not block the ingress model itself from being implemented.
