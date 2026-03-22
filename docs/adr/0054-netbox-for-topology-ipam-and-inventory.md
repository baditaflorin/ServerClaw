# ADR 0054: NetBox For Topology, IPAM, And Inventory

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.50.0
- Implemented In Platform Version: 0.26.0
- Implemented On: 2026-03-22
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

## Sources

- [What is NetBox?](https://netboxlabs.com/docs/netbox/en/stable/)
- [NetBox REST API](https://netboxlabs.com/docs/netbox/en/stable/integrations/rest-api/)

## Implementation Notes

- The repo now defines a dedicated NetBox automation surface through [playbooks/netbox.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/netbox.yml), [roles/netbox_postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/netbox_postgres), [roles/netbox_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/netbox_runtime), and [roles/netbox_sync](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/netbox_sync).
- [scripts/netbox_inventory_sync.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/netbox_inventory_sync.py) now synchronizes the canonical site, host, VM, prefix, IP address, and governed service inventory into the NetBox API with retry handling for transient runtime errors.
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json) now exposes `converge-netbox` as the canonical entry point with explicit preflight, validation, and verification metadata.
- [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json) now records the private NetBox API surface at `http://100.118.189.95:8004/api/`.
- Operator usage is documented in [docs/runbooks/configure-netbox.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-netbox.md).
- Live application is now verified from `main` through the Proxmox host Tailscale proxy at `http://100.118.189.95:8004`, with synchronized inventory covering the Hetzner site, the Proxmox host, all managed VMs, both canonical prefixes, primary IP assignments, and the governed service catalog.
