# ADR 0076: Subdomain Governance And DNS Lifecycle

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The platform publishes services under `lv3.org`. Subdomains have been added ad-hoc as services came online, with no defined process for: when to create a subdomain, what naming convention to follow, how TLS certificates are provisioned, or how a subdomain is retired when a service is removed.

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
<service>.<env>.lv3.org
```

- `<service>` — lowercase, hyphen-separated identifier matching the service's `id` in the service capability catalog (ADR 0075)
- `<env>` — omitted for production (e.g. `grafana.lv3.org`), included for staging (e.g. `grafana.staging.lv3.org`), and for any future additional environments
- special top-level subdomains (`mail.lv3.org`, `smtp.lv3.org`) are pre-reserved and documented in `config/subdomain-catalog.json`

Reserved subdomain prefixes that are never assigned to user-facing services:

- `_dmarc`, `_domainkey`, `dkim*` — mail authentication records
- `smtp`, `imap` — mail submission/retrieval
- `ops` — operations portal (ADR 0074)
- `internal` — reserved for internal routing only
- `staging` — staging wildcard delegation
- `api` — reserved for future internal API gateway

### Subdomain catalog

All active subdomains are recorded in `config/subdomain-catalog.json`:

```json
{
  "subdomains": [
    {
      "fqdn": "grafana.lv3.org",
      "service_id": "grafana",
      "environment": "production",
      "exposure": "edge-published",
      "target": "10.10.10.10",
      "target_port": 3000,
      "tls": {
        "provider": "letsencrypt",
        "cert_path": "/etc/letsencrypt/live/grafana.lv3.org/",
        "auto_renew": true
      },
      "created": "2026-01-15",
      "owner_adr": "0011"
    }
  ]
}
```

### TLS provisioning rules

| Exposure | TLS Provider | Certificate Type |
|---|---|---|
| `edge-published` | Let's Encrypt (ACME via Hetzner DNS-01) | Public DV certificate, auto-renewed |
| `private-only` | step-ca internal CA | Short-lived (90-day) internal certificate, auto-renewed |
| `informational-only` | None (DNS A record only, no HTTPS) | N/A |

Public subdomains use Hetzner DNS-01 challenge for Let's Encrypt so certificates can be provisioned without exposing a public HTTP-01 endpoint. The `roles/hetzner_dns_record` role handles DNS-01 token creation and cleanup.

Internal subdomains under `staging.lv3.org` are served by the staging step-ca intermediate; they are not publicly resolvable.

### Lifecycle process

**Creating a subdomain:**
1. add an entry to `config/subdomain-catalog.json`
2. add to the service capability catalog (ADR 0075)
3. run `make provision-subdomain fqdn=<name>` — this runs the DNS record role, provisions the TLS certificate, and adds the NGINX route
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

A wildcard certificate `*.lv3.org` is explicitly not used for production because:
- a single certificate compromise exposes all subdomains
- per-service certificates allow per-service revocation
- ACME DNS-01 issuance is automated and low-cost

For staging, `*.staging.lv3.org` issued by the internal step-ca is acceptable because staging is internal-only and certificates are short-lived.

## Consequences

- Every subdomain is catalogued before it can receive traffic; ungoverned DNS records cannot silently accumulate.
- The `make validate` gate includes a check that every NGINX route has a matching subdomain catalog entry.
- Certificate lifecycle is predictable and monitored; expiry surprises are eliminated.
- Retiring a service now has a defined subdomain teardown checklist.

## Boundaries

- This ADR covers subdomains under `lv3.org` only. Any future domain acquisitions require a separate ADR.
- DNSSEC and CAA records are security hardening steps documented in the security baseline runbook, not in this ADR.
- Internal `*.svc.cluster.local` style names used for container-to-container communication within a VM are not subdomains and are not governed by this ADR.
