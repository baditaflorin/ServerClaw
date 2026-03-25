# ADR 0144: Headscale For Zero-Trust Mesh VPN

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.146.3
- Implemented In Platform Version: 0.130.4
- Implemented On: 2026-03-25
- Date: 2026-03-25

## Context

ADR 0014 established the requirement for private operator access to the Proxmox host and the `10.10.10.0/24` guest network through a mesh VPN, with the Proxmox host acting as the subnet router.

The first live implementation used the hosted Tailscale control plane. That delivered private access quickly, but it left one critical control-plane dependency outside the repository:

- operator and server enrollment policy depended on a third-party admin console and API
- route approval and tag governance lived outside the repo-managed platform state
- the platform could not converge or recover its mesh-access control plane from first principles

At the same time, the current public-ingress topology already reserves host TCP `80/443` for DNAT into the NGINX edge VM at `10.10.10.10`, so any self-hosted control plane must fit behind that existing edge instead of bypassing it.

## Decision

We will run Headscale on the Proxmox host as the authoritative control plane for the LV3 mesh VPN while continuing to use the standard Tailscale client on servers and operator devices.

The deployed shape is:

- Headscale runs on `proxmox_florin` and listens privately on the host bridge address `10.10.10.1:8080`
- `headscale.lv3.org` is published through the existing NGINX edge VM rather than binding Headscale directly to the public host
- ACLs and route approvers are stored in the repository as a managed HuJSON policy
- the Proxmox host remains the user-owned subnet router for `10.10.10.0/24`
- operator devices and the Proxmox host authenticate to the mesh as the named `ops@` user in this phase
- the live cutover sequence is service-first, then Proxmox host migration, then operator-device migration, so the existing private path is not dropped prematurely

We will not enable the embedded DERP server in this phase. Clients continue to use the default upstream DERP map while the control plane and ACL authority move in-house.

## Consequences

- The zero-trust mesh control plane becomes repo-managed and recoverable from the platform codebase.
- The public ingress model remains consistent: NGINX is still the only public `80/443` edge.
- `management_tailscale_ipv4` remains the canonical management mesh address in repo truth, but it now comes from the Headscale-controlled network rather than the hosted Tailscale tailnet.
- Existing Tailscale-client automation stays usable after adding a configurable `--login-server`, but any operator lifecycle automation that talks directly to the hosted Tailscale SaaS API is now follow-on cleanup and must not be treated as the source of truth for the mesh.
