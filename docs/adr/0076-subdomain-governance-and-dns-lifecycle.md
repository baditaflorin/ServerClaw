# ADR 0076: Subdomain Governance And DNS Lifecycle

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.84.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

The platform publishes services under `example.com`. Subdomains have been added ad-hoc as services came online, with no defined process for: when to create a subdomain, what naming convention to follow, how TLS certificates are provisioned, or how a subdomain is retired when a service is removed.

Currently:
- DNS records are managed by `roles/hetzner_dns_record` and `roles/hetzner_dns_records` using the Hetzner DNS API
- NGINX edge routes are defined in `roles/nginx_edge_publication`
- TLS certificates are managed by step-ca (ADR 0042) for internal services and Let's Encrypt for public services
- There is no catalog of which subdomains exist, who owns them, and what their TLS status is
- Staging services have no subdomain model at all (addressed by ADR 0072)

As more services are added — especially the new platform apps (ops portal, changelog, agent workbench) — without a governance model, the subdomain space becomes unmanaged and TLS certificate coverage drifts.

## Decision

We will define a subdomain governance model covering naming, ownership, TLS provisioning, and lifecycle.

### Naming conventions

```
<service>.<env>.example.com
```

- `<service>` — lowercase, hyphen-separated identifier matching the service's `id` in the service capability catalog (ADR 0075)
- `<env>` — omitted for production (e.g. `grafana.example.com`), included for staging (e.g. `grafana.staging.example.com`), and for any future additional environments
- special top-level subdomains (`mail.example.com`, `smtp.example.com`) are pre-reserved and documented in `config/subdomain-catalog.json`

Reserved first-label prefixes are catalogued and enforced for future hostnames:

- `ops` — operations portal namespace (ADR 0074)
- `internal` — internal routing only
- `staging` — reserved environment namespace
- `api` — future governed API gateway
- `smtp`, `imap`, `mail` — mail transport and primary mail namespace

### Subdomain catalog

All active subdomains are recorded in `config/subdomain-catalog.json`:

```json
{
  "subdomains": [
    {
      "fqdn": "grafana.example.com",
      "service_id": "grafana",
      "environment": "production",
      "exposure": "edge-published",
      "target": "10.10.10.10",
      "target_port": 3000,
      "tls": {
        "provider": "letsencrypt",
        "cert_path": "/etc/letsencrypt/live/grafana.example.com/",
        "auto_renew": true
      },
      "created": "2026-01-15",
      "owner_adr": "0011"
    }
  ]
}
```

The catalog also records `reserved_prefixes` so the validator can reject new hostnames that would collide with governed namespaces unless the exact FQDN is explicitly allowlisted.

### TLS provisioning rules

| Exposure | TLS Provider | Certificate Type |
|---|---|---|
| `edge-published` | Let's Encrypt (ACME via Hetzner DNS-01) | Public DV certificate, auto-renewed |
| `private-only` | step-ca internal CA | Short-lived (90-day) internal certificate, auto-renewed |
| `informational-only` | None (DNS A record only, no HTTPS) | N/A |

Public subdomains use Hetzner DNS-01 challenge for Let's Encrypt so certificates can be provisioned without exposing a public HTTP-01 endpoint. The `roles/hetzner_dns_record` role handles DNS-01 token creation and cleanup.

Internal subdomains under `staging.example.com` are served by the staging step-ca intermediate; they are not publicly resolvable.

### Lifecycle process

**Creating a subdomain:**
1. add an entry to `config/subdomain-catalog.json`
2. add to the service capability catalog (ADR 0075)
3. run `make provision-subdomain FQDN=<name>` — this converges the DNS record and, when the hostname already has a repo-managed edge route, refreshes the shared NGINX publication and certificate set
4. verify the subdomain appears in the operations portal DNS map (ADR 0074)

**Retiring a subdomain:**
1. mark the entry in `config/subdomain-catalog.json` as `status: retiring`
2. update or remove the NGINX route
3. revoke the TLS certificate via step-ca or notify Let's Encrypt
4. remove the DNS record via `roles/hetzner_dns_record`
5. remove the catalog entry after 30 days

### Certificate expiry monitoring

The observation loop (ADR 0071) includes a `check-certificate-expiry` step that reads `config/subdomain-catalog.json` and alerts when any certificate is within 14 days of expiry. The subdomain catalog's `tls.cert_path` field is the input.

### Wildcard strategy

A wildcard certificate `*.example.com` is explicitly not used for production because:
- a single certificate compromise exposes all subdomains
- per-service certificates allow per-service revocation
- ACME DNS-01 issuance is automated and low-cost

For staging, `*.staging.example.com` issued by the internal step-ca is acceptable because staging is internal-only and certificates are short-lived.

## Consequences

- Every subdomain is catalogued before it can receive traffic; ungoverned DNS records cannot silently accumulate.
- The `make validate` gate now checks that every repo-managed NGINX route has a matching subdomain catalog entry and that reserved prefixes are enforced from the catalog itself.
- Certificate lifecycle is predictable and monitored; expiry surprises are eliminated.
- Retiring a service now has a defined subdomain teardown checklist.

## Boundaries

- This ADR covers subdomains under `example.com` only. Any future domain acquisitions require a separate ADR.
- DNSSEC and CAA records are security hardening steps documented in the security baseline runbook, not in this ADR.
- Internal `*.svc.cluster.local` style names used for container-to-container communication within a VM are not subdomains and are not governed by this ADR.
