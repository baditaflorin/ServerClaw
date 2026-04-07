# ADR 0015: lv3.org DNS And Subdomain Model

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: 0.5.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

This platform will use `lv3.org` as its public DNS zone.

The platform design already assumes multiple named entry points for services such as:

- Proxmox management
- Grafana monitoring
- NGINX ingress
- Docker runtime-facing services
- build access and related operator workflows

The DNS model needs to support two realities:

1. services will be introduced incrementally
2. DNS names should be stable before the final ingress routing is complete

At the time of writing:

- the zone `lv3.org` already exists in Hetzner DNS
- the root `A` record points to `65.108.75.123`
- the existing root and `www` `AAAA` records do not match the current server IPv6 and should be treated as drift until explicitly corrected

## Decision

We will use named subdomains under `lv3.org` for platform entry points.

Initial records to create now:

- `proxmox.lv3.org`
- `grafana.lv3.org`
- `nginx.lv3.org`
- `docker.lv3.org`
- `build.lv3.org`

Initial record type policy:

- create `A` records to the Proxmox host public IPv4 `65.108.75.123`
- do not create new `AAAA` records until IPv6 routing and service exposure are intentionally validated

Traffic intent:

- these names may initially terminate on the Proxmox host public IP
- over time, public HTTP/HTTPS traffic should be forwarded or proxied deliberately to the NGINX VM at `10.10.10.10`
- private workloads remain private by policy even if their public DNS names exist in advance

## Consequences

- DNS names become stable early, which reduces churn in certificates, configs, dashboards, and operator habits.
- The initial records can point at the host while the guest routing model is still being implemented.
- IPv6 publication is intentionally delayed to avoid shipping incorrect public resolution.

## Follow-up requirements

This ADR still requires:

- cleanup or correction of the existing stale `AAAA` records
- TLS and reverse-proxy routing for each public hostname
- a decision on whether some hostnames should remain internal-only in steady state
