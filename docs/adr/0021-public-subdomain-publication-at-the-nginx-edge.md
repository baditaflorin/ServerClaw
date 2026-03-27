# ADR 0021: Public Subdomain Publication At The NGINX Edge

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.22.0
- Implemented In Platform Version: 0.14.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

ADR 0013 established that the NGINX VM at `10.10.10.10` is the single public edge for HTTP and HTTPS traffic.

ADR 0015 established the stable DNS names:

- `proxmox.lv3.org`
- `grafana.lv3.org`
- `nginx.lv3.org`
- `docker.lv3.org`
- `build.lv3.org`

In live operation, those names all reached the same default Debian NGINX page. That is misleading because the hostnames imply distinct services and exposure intent.

At the same time, not every named service should be made public just because a public DNS record exists.

## Decision

We will publish subdomains deliberately at the NGINX edge.

Publication rules:

1. `grafana.lv3.org`
   - publicly reverse proxy to Grafana on `10.10.10.40:3000`
2. `nginx.lv3.org`
   - serve an explicit edge landing page from the NGINX VM
3. `proxmox.lv3.org`
   - serve an explicit informational page stating that Proxmox administration remains private and is reached over Tailscale
4. `docker.lv3.org`
   - serve an explicit informational page stating that the Docker runtime VM has no public web service by default
5. `build.lv3.org`
   - serve an explicit informational page stating that the build VM is private and operator-facing, not a public web workload

TLS handling:

- the NGINX edge should obtain a Let's Encrypt certificate for the published hostnames
- HTTP should redirect to HTTPS once the certificate is in place

## Consequences

- Hostnames stop collapsing onto a misleading catch-all page.
- Grafana becomes intentionally published at the edge.
- Proxmox, Docker runtime, and build remain non-public workloads while still having truthful public hostnames.
- Public exposure decisions stay centralized at the NGINX VM instead of leaking into guest-by-guest one-offs.

## Follow-up requirements

- If Docker runtime or build later need public application endpoints, create a dedicated ADR or update this one with the exact publication model.
- If Proxmox UI should ever be published directly, that requires a separate decision because it changes the current security posture materially.
