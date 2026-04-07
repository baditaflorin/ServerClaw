# ADR 0010: Initial Proxmox VM Topology

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: 0.6.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

This Proxmox host is intended to run multiple VMs with clear separation of responsibilities instead of collapsing all workloads into one general-purpose guest.

The first required guests are:

- `10.10.10.10`: NGINX VM
- `10.10.10.20`: general Docker runtime VM for long-running containers
- `10.10.10.30`: Docker build VM for remote interactive build work from laptops and other operator machines
- `10.10.10.40`: monitoring VM

The build VM needs materially higher compute capacity than the general runtime VM because it will be used for image builds and other bursty CPU-heavy work.

## Decision

We will start with a simple four-VM topology on a private Proxmox-managed network in the `10.10.10.0/24` range.

Initial guest roles:

1. NGINX VM
   - IP: `10.10.10.10`
   - purpose: reverse proxy, ingress, TLS termination, and public edge routing
2. Docker runtime VM
   - IP: `10.10.10.20`
   - purpose: run long-lived application containers and supporting services
3. Docker build VM
   - IP: `10.10.10.30`
   - purpose: remote Docker builds and other operator-driven build tasks
   - initial size target: `12` vCPU and `24 GB` RAM
4. Monitoring VM
   - IP: `10.10.10.40`
   - purpose: Grafana, platform monitoring, and supporting telemetry services

## Network model

We will create a Proxmox bridge-backed internal network for guest-to-guest communication and controlled ingress exposure.

Design intent:

- guests communicate over `10.10.10.0/24`
- NGINX is the public-facing ingress point
- Docker runtime and Docker build VMs are not treated as directly public workloads by default
- external access to the build VM should be deliberate and restricted to known operator/admin paths

## Operational model

The VMs will have intentionally different lifecycle expectations:

- NGINX VM should stay small, stable, and easy to rebuild
- Docker runtime VM should optimize for service continuity and predictable resource use
- Docker build VM should optimize for throughput and can tolerate more aggressive maintenance and rebuild patterns

## Consequences

- We keep edge routing isolated from general container execution.
- We avoid mixing build workloads with production-style runtime workloads.
- We preserve a clean place to apply different security controls, backup policies, and maintenance windows per VM role.
- Future additions such as monitoring, CI runners, databases, or VPN/bastion VMs should be introduced as separate roles rather than overloaded into these first three guests.

## Follow-up requirements

This ADR defines topology intent only. Follow-up automation and ADRs should still define:

- Proxmox bridge and VLAN design
- public ingress and NAT/routing approach
- guest templates and cloud-init strategy
- backup policy per VM
- security controls for operator access to the build VM
