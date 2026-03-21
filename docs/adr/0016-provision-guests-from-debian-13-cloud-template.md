# ADR 0016: Provision Guests From Debian 13 Cloud Template

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.6.0
- Implemented In Platform Version: 0.6.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

The network and platform prerequisites now exist on the Proxmox host:

- Proxmox VE is installed and reachable
- `vmbr10` provides the internal `10.10.10.0/24` guest network
- host-side NAT already gives private guests outbound internet access

The next high-value step is to create the first guest set from code instead of creating VMs manually in the Proxmox UI.

## Decision

We will provision the first guests from a reusable Debian 13 cloud-image template using Proxmox `qm` plus cloud-init.

Provisioning model:

1. Build one reusable Debian 13 cloud template on the Proxmox host
2. Clone all initial guests from that template
3. Set guest IPs, resources, and first-boot user-data from version-controlled definitions
4. Keep the provisioning path idempotent enough to re-run safely

Initial guest set:

1. `10.10.10.10` NGINX VM
   - VMID: `110`
   - role: edge/reverse proxy
2. `10.10.10.20` Docker runtime VM
   - VMID: `120`
   - role: long-running application containers
3. `10.10.10.30` Docker build VM
   - VMID: `130`
   - role: build-heavy remote operator workflows
   - target size: `12` vCPU, `24 GB` RAM
4. `10.10.10.40` monitoring VM
   - VMID: `140`
   - role: Grafana and supporting monitoring services

## Why this model

This model is preferred because it is:

- reproducible
- fast to rebuild
- easy to review in git
- consistent with the agent-oriented operating model

It also creates a clean separation between:

- VM lifecycle provisioning
- guest operating-system bootstrap
- workload configuration inside the guests

## Consequences

- Manual one-off guest creation in the Proxmox UI is no longer the preferred path.
- Guest definitions become part of the repository contract.
- Cloud-init becomes a required part of the first-boot guest experience.
- Workload configuration inside the guest can evolve independently from VM creation semantics.

## Follow-up requirements

This ADR still requires implementation details for:

- exact VM resource assignments beyond the build VM minimum
- first-boot user-data contents
- template image checksum pinning
- how guest backups and autostart are enforced
