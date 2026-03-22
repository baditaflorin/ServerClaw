# ADR 0054: NetBox For Topology, IPAM, And Inventory

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository already contains machine-readable topology and status data, but there is no dedicated visual system for:

- networks and subnets
- VM and service inventory
- ownership and role metadata
- cable or dependency-style infrastructure views
- browsing infrastructure state without reading several YAML files

Humans can read the repo. Agents can read the repo. Both still benefit from a visual inventory plane that exposes the same information in a navigable form.

## Decision

We will use NetBox as the visual infrastructure inventory and IPAM plane.

Initial responsibilities:

1. represent sites, devices, virtual machines, interfaces, IP addresses, and prefixes
2. expose ownership, role, and status metadata in one UI
3. provide topology and address visibility for operators and agents
4. receive synchronized data from canonical repo sources where practical
5. act as the visual inventory plane for future automation integrations

Initial scope:

- Hetzner host
- Proxmox node
- VM inventory
- bridges and private networks
- public and private IP assignments
- major control-plane applications and their owners

## Consequences

- Operators gain a visual topology and address-management interface that complements the repository.
- Agents can query a structured inventory API instead of scraping prose docs.
- Inventory drift becomes easier to detect when repo intent and NetBox state disagree.
- A synchronization boundary is required so NetBox does not silently become an unsupervised second source of truth.

## Boundaries

- The repository remains authoritative for planned infrastructure changes unless a follow-up ADR explicitly changes that rule.
- NetBox is not the workflow runtime and must not become a hidden mutation surface for unrelated platform behavior.
