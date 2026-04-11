# ADR 0015: example.com DNS And Subdomain Model

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: 0.5.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

This platform will use `example.com` as its public DNS zone.

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

- the zone `example.com` already exists in Hetzner DNS
- the root `A` record points to `203.0.113.1`
- the existing root and `www` `AAAA` records do not match the current server IPv6 and should be treated as drift until explicitly corrected

## Decision

We will use named subdomains under `example.com` for platform entry points.

Initial records to create now:

- `proxmox.example.com`
- `grafana.example.com`
- `nginx.example.com`
- `docker.example.com`
- `build.example.com`

Initial record type policy:

- create `A` records to the Proxmox host public IPv4 `203.0.113.1`
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
