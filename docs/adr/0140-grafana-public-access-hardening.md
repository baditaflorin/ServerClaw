# ADR 0140: Grafana Public Access Hardening

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Grafana is currently deployed at `grafana.lv3.org` with Keycloak OIDC authentication integrated. However, the Grafana configuration retains its default `allow_embedding = false` setting and has an unreviewed anonymous access policy. The platform's public-facing status information has historically been provided via Grafana dashboards that were occasionally shared or linked publicly.

The specific risks in the current Grafana deployment:

**Anonymous viewer access**: Grafana's `GF_AUTH_ANONYMOUS_ENABLED` setting may be enabled from previous operational decisions or default configuration. Anonymous access exposes all dashboards marked "public" to anyone who reaches `grafana.lv3.org`, including metric labels that enumerate internal service names, VM names, container names, and Ansible role targets.

**Metric label enumeration**: Prometheus metric labels (used in Grafana panel queries) include values like `job="netbox"`, `host="postgres-lv3"`, `container_name="windmill_worker"`, `ansible_role="nginx_edge_publication"`. These labels, visible in panel inspect mode, reveal the full internal service inventory to any dashboard viewer.

**Dashboard URL sharing**: Grafana dashboard URLs contain the dashboard UID and can include panel data URLs with time ranges. These URLs, if shared externally, allow anyone with the URL to view the data if anonymous access is enabled.

**Grafana API key exposure**: Older Grafana deployments use long-lived API keys for dashboard automation. Any unexpired API key provides read access to all dashboards.

**Plugin version disclosure**: Grafana's `X-Grafana-Version` response header and the `/api/health` endpoint expose the exact Grafana version, enabling CVE correlation.

## Decision

We will harden the Grafana deployment with four specific changes:

### Change 1: Disable anonymous access

```ini
# In Grafana's grafana.ini (managed by Ansible role)
[auth.anonymous]
enabled = false

[auth]
disable_login_form = false    # Keep login form for bootstrap recovery
```

All access requires Keycloak OIDC authentication via the oauth2-proxy sidecar, consistent with ADR 0133.

### Change 2: Remove public dashboard sharing

Grafana's "public dashboard" feature (introduced in Grafana 10) allows generating share links that bypass authentication. This feature is disabled:

```ini
[public_dashboards]
enabled = false
```

Any existing public dashboard share links are revoked by rotating the signing key:
```bash
# In the converge-grafana workflow
grafana-cli admin reset-public-dashboards-signing-key
```

### Change 3: Strip version headers at the nginx proxy

```nginx
# In the grafana.lv3.org vhost
proxy_hide_header X-Grafana-Version;
proxy_hide_header Via;

# The /api/health endpoint exposes version; restrict to authenticated requests only
location = /api/health {
    auth_request /oauth2/auth;
    error_page 401 =404 /dev/null;
    proxy_pass http://grafana:3000;
}
```

### Change 4: API key to service account migration

Grafana API keys are deprecated in favour of service accounts with short-lived tokens. Any existing API keys are audited and rotated to service account tokens:

```bash
# Audit existing API keys
$ lv3 run grafana-api-key-audit

# Expected output: all keys migrated to service accounts; no long-lived keys remain
```

Service account tokens are stored in OpenBao (ADR 0043) with a 90-day TTL and automated rotation (ADR 0065).

### Status page migration

The only legitimate public use of Grafana was providing a status page. This is already migrated to `status.lv3.org` (ADR 0109). Any remaining Grafana panels intended for public display must be moved to the status page service before anonymous access is disabled. A migration checklist:

- [ ] Identify all Grafana panels referenced from `status.lv3.org` or external links.
- [ ] Migrate panel data to the status page service API.
- [ ] Remove public share links for all migrated panels.
- [ ] Disable anonymous access.

### Grafana provisioning security

Grafana datasource configurations managed by Ansible (`config/grafana/datasources/*.yaml`) must not contain raw Prometheus credentials. These files are committed to the repository and must reference OpenBao paths rather than embedding values:

```yaml
# Correct: reference OpenBao path
datasources:
  - name: Prometheus
    url: http://prometheus:9090
    basicAuthPassword: $__env{GF_PROMETHEUS_PASSWORD}  # Injected from OpenBao at startup
```

## Consequences

**Positive**

- Metric label enumeration is no longer possible for unauthenticated actors. The full internal service inventory is no longer accessible by anyone who reaches `grafana.lv3.org`.
- Public dashboard share links cannot leak via operator error (e.g., posting a shared link in a public forum while asking for help).
- Version strings are no longer available via HTTP headers, reducing CVE correlation exposure.

**Negative / Trade-offs**

- Any external service that used Grafana public dashboards (e.g., a status embed on a personal website or a shared monitoring link with a colleague) will break. These use cases should be migrated to the status page API (ADR 0109) which is designed for public consumption.
- Disabling the public dashboard API key requires an audit of all automation that uses Grafana API keys. If any monitoring or backup tool uses an API key for dashboard exports, it must be migrated to a service account before the key is revoked.

## Boundaries

- This ADR hardens the existing Grafana deployment. It does not change the observability architecture (what is measured, what alerts fire, what dashboards exist).
- The status page (ADR 0109) remains public; this ADR moves the data source for public status from Grafana to the status page service.

## Related ADRs

- ADR 0011: Grafana dashboards (deployment configuration)
- ADR 0043: OpenBao (service account token storage)
- ADR 0056: Keycloak SSO (OIDC for Grafana auth)
- ADR 0065: Secret rotation (Grafana service account token rotation)
- ADR 0109: Public status page (migration destination for public panels)
- ADR 0133: Portal authentication by default (anonymous access removal; consistent policy)
- ADR 0136: HTTP security headers (version header stripping complemented here)
- ADR 0137: Robots and crawl policy (noindex for grafana.lv3.org)
