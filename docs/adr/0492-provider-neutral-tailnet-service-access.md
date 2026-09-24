# ADR 0492: Provider-Neutral Tailnet Service Access

- Status: Accepted
- Implementation Status: Partial
- First Repo Version: `0.179.47`
- First Platform Version: pending live apply (baseline `0.178.222`)
- Implemented On: 2026-09-24 (repository configuration merged; live application pending)
- Date: 2026-09-24

## Context

The service model has a `private-only` exposure class and the Proxmox topology
can route individual services through a Tailscale TCP proxy. That does not
clearly distinguish an ordinary private-network service from one intended to
be reachable only through an operator tailnet. The Proxmox Tailscale client
also accepts a custom login server, but the deployment selects it through an
implicit host variable rather than a validated provider choice.

Operators need to choose hosted Tailscale or a self-hosted control plane while
keeping a tailnet-only service declaration independent of that provider. In
particular, choosing Headscale must not imply replacing the Tailscale client.

## Decision

- Add an optional `mesh_access: tailnet` field to service definitions. It is
  valid only for `private-only` services with repo-declared tailnet-scoped DNS
  and a managed Tailscale TCP proxy path.
- Add flat Proxmox host variables for the mesh control-plane provider and login
  server. Hosted Tailscale uses provider `tailscale` with no custom login
  server; Headscale uses provider `headscale` and an HTTPS login-server URL.
- Validate this provider/URL pair before the managed client can refresh its
  state. The same Tailscale client remains in use for either control plane.
- Compare the active control-server URL with the selected provider and refuse
  an implicit migration of an enrolled node. A separate explicit flag is
  required for a planned control-plane cutover.
- Do not change tailnet ACLs, node enrollment, DNS, or live control-plane state
  as part of selecting or declaring the configuration.

## Consequences

- A service catalog entry can say explicitly that network membership is part
  of its access boundary without conflating that boundary with public exposure.
- Fork operators can select self-hosted Headscale or hosted Tailscale through
  deployment configuration, while invalid combinations fail closed.
- Headscale removes the hosted Tailscale control-plane dependency but keeps
  Tailscale-compatible clients. A distinct mesh such as NetBird is not a
  drop-in control-plane choice and needs a separate client, route, policy, and
  service-proxy integration before it can be selected here.
- A provider setting cannot silently migrate an already enrolled node between
  control planes.
- A tailnet-only hostname still requires a separately managed split-DNS or
  private routing arrangement; this ADR does not make public DNS a private
  access-control mechanism.
- Existing live mesh enrollment and ACL policy remain unchanged until a
  separately reviewed live operation.

## Alternatives considered

- Reuse `private-only` alone: rejected because it does not state whether access
  is LAN-only or tailnet-only.
- Add `tailnet-only` to the exposure enum: rejected because network membership
  and public-edge exposure are separate axes.
- Replace the Tailscale client with a different client when selecting
  Headscale: rejected because Headscale is a compatible control plane and the
  existing Tailscale client remains the data-plane client.
- Add a different mesh implementation in this change: deferred because an
  independent client/control plane needs a separately reviewed provider
  adapter and cannot reuse the Tailscale TCP-proxy contract by renaming it.

## Implementation state

The first repository version is pending merge. No platform version or
implementation date is claimed until the configuration is applied and verified
on a live deployment.
