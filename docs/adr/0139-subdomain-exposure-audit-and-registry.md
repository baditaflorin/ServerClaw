# ADR 0139: Subdomain Exposure Audit and Registry

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

`config/subdomain-catalog.json` (ADR 0076) is the declared inventory of all subdomains. However, there is currently no automated mechanism that verifies:

1. That the catalog matches the DNS records that actually exist in the Hetzner DNS zone.
2. That every live subdomain has a corresponding nginx vhost with the correct authentication tier.
3. That no subdomain has been added to DNS or nginx without a catalog entry (shadow subdomains).
4. That the `auth_requirement` field (ADR 0133) reflects the actual nginx configuration deployed to the host.

The gap is drift between the declared intent (catalog) and the deployed reality (DNS zone, nginx config). This drift can occur when:

- An operator adds a temporary subdomain for testing and forgets to remove it.
- An Ansible run partially applies a new vhost without completing the catalog update.
- A break-glass procedure creates an emergency subdomain that is never cleaned up.
- A third-party app (Keycloak, Grafana, Windmill) registers a callback URL that resolves through the nginx proxy under an undeclared path.

Shadow subdomains are a common initial access vector: an attacker finds a forgotten test subdomain that bypasses the main platform's security controls because it was created before those controls existed.

## Decision

We will implement a **weekly subdomain exposure audit** as a Windmill workflow that compares the DNS zone, nginx configuration, and subdomain catalog and alerts on any discrepancy.

### Audit checks

**Check 1: DNS zone vs. catalog**

Query the Hetzner DNS API for all A/AAAA/CNAME records under `lv3.org`. For each record:
- If it appears in `config/subdomain-catalog.json`: OK.
- If it does not appear in the catalog: emit `security.undeclared_subdomain` finding.
- If it is in the catalog but not in DNS: emit `ops.subdomain_in_catalog_missing_from_dns` finding (likely not yet deployed, acceptable).

**Check 2: nginx vhost vs. catalog**

Read the deployed nginx vhost configuration from the nginx-lv3 VM (via Ansible facts or SSH). For each `server_name` block:
- If it appears in the catalog with matching `auth_requirement`: OK.
- If `auth_requirement` in catalog is `keycloak_oidc` but the vhost has no `auth_request`: emit `security.portal_missing_auth` finding (CRITICAL).
- If it does not appear in the catalog: emit `security.undeclared_nginx_vhost` finding.

**Check 3: auth_requirement drift**

For each catalog entry with `auth_requirement: keycloak_oidc`:
- Make an unauthenticated HTTP request to the subdomain.
- If the response is not a redirect to `sso.lv3.org/realms/lv3/protocol/openid-connect/auth`: emit `security.portal_auth_not_enforced` finding (CRITICAL).

**Check 4: TLS certificate validity**

For each catalog entry with `tls: letsencrypt` or `tls: step-ca`:
- Check that a valid TLS certificate is served.
- If expired or expiring within 14 days: emit `ops.cert_expiry_imminent` finding (already covered by ADR 0071 but duplicated here for completeness).

### Output format

```json
{
  "audit_run_id": "uuid",
  "audited_at": "2026-03-24T14:00Z",
  "subdomains_in_catalog": 12,
  "dns_records_checked": 14,
  "nginx_vhosts_checked": 12,
  "findings": [
    {
      "check": "dns_vs_catalog",
      "severity": "CRITICAL",
      "subdomain": "dev.lv3.org",
      "finding": "undeclared_subdomain",
      "detail": "DNS A record points to 10.10.10.10 but no catalog entry exists"
    }
  ]
}
```

CRITICAL-severity findings publish `platform.security.exposure_audit_alert` to NATS (ADR 0124), post to Mattermost `#platform-security`, and open a GlitchTip incident (ADR 0061).

### Catalog schema extension

The `auth_requirement` field (ADR 0133) is added to `config/subdomain-catalog.json`:

```json
{
  "subdomain": "changelog",
  "fqdn": "changelog.lv3.org",
  "audience": "operators",
  "auth_requirement": "keycloak_oidc",
  "tls": "letsencrypt",
  "nginx_vhost": "changelog.conf.j2",
  "registered_at": "2026-03-24",
  "registered_by": "adr-0081"
}
```

The validation pipeline (ADR 0031) rejects any `subdomain-catalog.json` entry missing `auth_requirement`.

### DNS zone snapshot

The audit workflow writes a snapshot of the full DNS zone to `receipts/dns-audit/YYYY-MM-DD.json` after each run. This provides a durable history of what subdomains were live at each point in time, useful for incident investigation ("was this subdomain live during the incident?").

### Operator CLI

```bash
$ lv3 run subdomain-audit
Running subdomain exposure audit...

✓ catalog:    12 entries
✓ dns:        12 records (all declared)
✓ nginx:      12 vhosts (all match catalog)
✓ auth:       12/12 authenticated portals enforce redirect

⚠ cert expiry: step-ca.lv3.org expires in 12 days (scheduled renewal pending)

No CRITICAL findings. Full report: receipts/dns-audit/2026-03-24.json
```

## Consequences

**Positive**

- Shadow subdomains created outside the normal governance process are detected within 7 days. The window for an undiscovered test subdomain to become an attack vector is bounded.
- The unauthenticated probe (Check 3) provides external verification that the authentication deployment is actually working, not just declared in config.
- The DNS zone snapshot history enables forensic analysis of subdomain changes over time.

**Negative / Trade-offs**

- The unauthenticated HTTP probes in Check 3 require the workflow to make requests to the live subdomains from within the platform (or via a publicly routable path). If the nginx edge is behind a firewall that blocks the workflow's source IP, Check 3 will produce false negatives. The workflow should run from the nginx-lv3 VM itself or from an external probe.
- Weekly frequency means a shadow subdomain could exist for up to 7 days before detection. For higher assurance, the DNS check (Check 1) can run daily since it only requires an API call to Hetzner DNS, not a live HTTP probe.

## Boundaries

- This ADR audits subdomains under `lv3.org`. It does not audit wildcard certificates, SAN entries on step-ca-issued certs, or subdomains under other domains owned by the operator.
- The audit is detective, not preventive. It detects drift after it occurs; prevention requires disciplined use of the catalog-first workflow for all subdomain additions.

## Related ADRs

- ADR 0031: Repository validation pipeline (auth_requirement field validation)
- ADR 0042: step-ca (TLS cert validity check)
- ADR 0057: Mattermost (CRITICAL finding notifications)
- ADR 0061: GlitchTip (CRITICAL findings open incidents)
- ADR 0076: Subdomain governance (catalog schema extended here)
- ADR 0081: Deployment changelog portal (changelog.lv3.org entry in catalog)
- ADR 0094: Developer portal (docs.lv3.org entry in catalog)
- ADR 0124: Platform event taxonomy (platform.security.exposure_audit_alert)
- ADR 0133: Portal authentication by default (auth_requirement field; Check 3 validates enforcement)
