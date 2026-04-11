# ADR 0144: Headscale For Zero-Trust Mesh VPN

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.148.1
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

- Headscale runs on `proxmox-host` and listens privately on the host bridge address `10.10.10.1:8080`
- `headscale.example.com` is published through the existing NGINX edge VM rather than binding Headscale directly to the public host
- ACLs and route approvers are stored in the repository as a managed HuJSON policy
- the Proxmox host remains the user-owned subnet router for `10.10.10.0/24`
- operator devices and the Proxmox host authenticate to the mesh as the named `ops@` user in this phase
- the live cutover sequence is service-first, then Proxmox host migration, then operator-device migration, so the existing private path is not dropped prematurely

We will not enable the embedded DERP server in this phase. Clients continue to use the default upstream DERP map while the control plane and ACL authority move in-house.

## Replaceability Scorecard

- Capability Definition: `mesh_access_control_plane` as defined by ADR 0014 private guest-network access, ADR 0046 identity classes, and the Headscale runbook.
- Contract Fit: strong for self-hosted node enrollment, ACL policy, subnet-route approval, and repo-governed operator access while keeping the standard Tailscale client on endpoints.
- Data Export / Import: ACL policy, tag and route approvals, auth-key policy, node inventory, and operator enrollment guidance are portable enough to seed another mesh control plane.
- Migration Complexity: medium because every enrolled node, subnet router, and operator device must be rehomed carefully without dropping the canonical private management path.
- Proprietary Surface Area: medium because Tailnet-compatible control-plane semantics and upstream DERP dependence still shape policy and client behavior.
- Approved Exceptions: continued use of the upstream DERP map and the Tailscale client protocol are accepted so long as enrollment policy, ACLs, and route approval remain repo-managed.
- Fallback / Downgrade: the managed Tailscale SaaS control plane can carry the minimum operator-access path again if a replacement self-hosted controller cannot be cut over in time.
- Observability / Audit Continuity: node inventory, ACL policy history, route status, mesh health probes, and host access receipts remain the continuity surface during migration.

## Vendor Exit Plan

- Reevaluation Triggers: client-protocol breakage, insufficient ACL or auth-key governance, unacceptable operational overhead, or a need for relay and routing controls Headscale cannot provide cleanly.
- Portable Artifacts: HuJSON ACL policy, node and route inventory, auth-key policy, enrollment procedures, and subnet-router topology notes.
- Migration Path: stand up the replacement control plane in parallel, mint new enrollment material, migrate the subnet router and one operator device first, move the remaining nodes by wave, and retire Headscale only after the private management path is stable on the replacement.
- Alternative Product: managed Tailscale or NetBird.
- Owner: platform networking.
- Review Cadence: quarterly.

## Consequences

- The zero-trust mesh control plane becomes repo-managed and recoverable from the platform codebase.
- The public ingress model remains consistent: NGINX is still the only public `80/443` edge.
- `management_tailscale_ipv4` remains the canonical management mesh address in repo truth, but it now comes from the Headscale-controlled network rather than the hosted Tailscale tailnet.
- Existing Tailscale-client automation stays usable after adding a configurable `--login-server`, but any operator lifecycle automation that talks directly to the hosted Tailscale SaaS API is now follow-on cleanup and must not be treated as the source of truth for the mesh.
