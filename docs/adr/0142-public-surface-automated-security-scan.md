# ADR 0142: Public Surface Automated Security Scan

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform's public attack surface consists of:
- TCP 25/587/993 (SMTP/submission/IMAPS) via Proxmox host DNAT to the mail VM.
- TCP 80/443 via nginx-lv3, serving all published subdomains.
- The Hetzner-managed DNS zone (indirectly; DNS misconfiguration can redirect traffic).

The current security controls (authentication gates, HSTS, CSP, secret scanning) are all **preventive**: they are designed to prevent vulnerabilities. What is missing is a **detective** layer that periodically scans the live public surface from the outside to verify that the preventive controls are actually deployed correctly and that no new vulnerabilities have been introduced.

In practice:
- An Ansible role update might accidentally remove the `auth_request` directive from a vhost.
- A Grafana upgrade might re-enable anonymous access via its migration of `grafana.ini`.
- A misconfigured Let's Encrypt renewal might result in an expired certificate being served.
- A new nginx `location` block added for a webhook might inadvertently bypass authentication for a path prefix.
- A TLS misconfiguration might accept weak cipher suites that were previously disabled.

These issues would all be caught immediately if there were an automated external scan. Without one, they could persist until an operator manually checks or an external report arrives.

## Decision

We will implement an **automated public surface security scan** that runs weekly using open-source scanning tools (`nuclei`, `testssl.sh`) against the live platform, with findings emitted to the security findings pipeline.

### Scan components

**Component 1: TLS configuration scan (`testssl.sh`)**

Run against every HTTPS subdomain in the catalog with `audience: public` or `audience: operators`:

```bash
testssl.sh \
  --quiet \
  --jsonfile /tmp/tls-scan-${subdomain}.json \
  --severity LOW \
  --protocols \
  --ciphers \
  --headers \
  --vulnerability \
  https://${subdomain}.lv3.org
```

Findings mapped to severity:
- Expired certificate → CRITICAL
- TLSv1.0 or TLSv1.1 accepted → HIGH
- Weak cipher suite accepted → HIGH
- Missing HSTS → MEDIUM
- Missing HSTS preload → LOW
- CBC cipher preference → LOW

**Component 2: HTTP security headers scan (in-house)**

For each subdomain, make an unauthenticated GET request and check for required headers (ADR 0136):

```python
required_headers = {
    "Strict-Transport-Security": lambda v: "max-age=63072000" in v,
    "X-Content-Type-Options":    lambda v: v == "nosniff",
    "X-Frame-Options":           lambda v: v in ("DENY", "SAMEORIGIN"),
    "Referrer-Policy":           lambda v: "strict-origin" in v,
    "X-Robots-Tag":              lambda v: "noindex" in v,
}
```

**Component 3: Authentication bypass check**

For every subdomain with `auth_requirement: keycloak_oidc`, send an unauthenticated GET request and verify that:
- The response is an HTTP 302 redirect to `sso.lv3.org`.
- The response body does not contain any portal content (no `<html>` with dashboard content).
- The response does not include any sensitive headers (e.g., `X-Auth-Request-User`).

**Component 4: Version string disclosure check**

For each public subdomain, check that the response headers do not include:
- `X-Powered-By`, `Server` (containing application name/version), `X-Grafana-Version`, `X-Windmill-Version`, or any header matching the pattern `X-.*-Version`.

**Component 5: Open redirect check (`nuclei`)**

```bash
nuclei \
  -target https://lv3.org \
  -tags redirect,misconfig \
  -severity medium,high,critical \
  -json \
  -o /tmp/nuclei-results.json
```

Checks for common open redirect patterns in the oauth2-proxy and Keycloak login flows.

### Scan runner

The scan runs as a Windmill workflow `weekly-security-scan` on a weekly schedule. It runs from the `docker-build-lv3` VM (which has egress to the public internet) to simulate an external attacker's view.

For `testssl.sh` and `nuclei`, the workflow pulls the latest versions at scan time and runs them in an ephemeral Docker container (consistent with ADR 0083's check-runner pattern).

### Finding classification and output

| Finding severity | Action |
|---|---|
| CRITICAL | Immediate Mattermost `#platform-security` alert, GlitchTip incident, ledger event, triage loop activation |
| HIGH | Mattermost `#platform-security` alert, ledger event; operator acknowledgement required within 24h |
| MEDIUM | Ledger event; included in weekly security summary |
| LOW | Included in weekly security summary only |

The weekly security summary is posted to `#platform-security` as a formatted Mattermost message every Monday:

```
📊 Weekly security scan: lv3.org

Scanned: 8 subdomains | Duration: 4m 12s
TLS: ✓ All certs valid (min expiry: 45d on step-ca.lv3.org)
Headers: ✓ All required headers present
Auth: ✓ All protected portals enforce redirect
Versions: ✓ No version strings disclosed
Redirects: ✓ No open redirects detected

CRITICAL findings: 0
HIGH findings: 0
MEDIUM findings: 0
Full report: receipts/security-scan/2026-03-24.json
```

### Exclusion list

The scan explicitly excludes:
- The mail ports (25, 587, 993): these have dedicated monitoring elsewhere.
- Any scan class that could be interpreted as an active attack (e.g., SQL injection, fuzzing): this is an automated scan of a production system, not a penetration test.
- Port scans beyond 80/443: out of scope for this ADR; see firewall policy (ADR 0067).

## Consequences

**Positive**

- Regressions in security controls (accidentally removed auth gate, re-enabled anonymous Grafana access, expired certificate) are detected within one week rather than when an operator notices or an external report arrives.
- The scan results provide continuous external verification of the controls defined in ADRs 0133–0141.
- The weekly summary provides operators with a low-noise, regular attestation that the public surface is in the expected state.

**Negative / Trade-offs**

- Running `nuclei` against a live system, even without active exploitation checks, generates log noise on the nginx access log that looks like a scan. This is expected and acceptable, but operators should be aware that the scan is the source of these requests.
- The scan runs from within the platform (`docker-build-lv3`). It does not test what an attacker from an entirely different network sees (e.g., CDN-cached responses, Hetzner DDoS scrubbing effects). A periodic manual probe from an external VPS would provide complementary coverage.

## Boundaries

- This ADR defines automated scanning of the public HTTP/HTTPS surface. It does not cover internal network security scanning, database security, or application-layer penetration testing.
- Findings from this scan are advisory for LOW and MEDIUM severity. CRITICAL and HIGH findings trigger the incident response pipeline (ADR 0126) automatically.
- This is not a penetration test. Active exploitation attempts, payload injection, and authenticated scanning are explicitly excluded.

## Related ADRs

- ADR 0057: Mattermost (security findings notifications)
- ADR 0061: GlitchTip (CRITICAL findings → incident)
- ADR 0067: Guest network policy (firewall; separate from this surface scan)
- ADR 0083: Docker-based check runner (container execution model for scan tools)
- ADR 0115: Event-sourced mutation ledger (scan findings recorded)
- ADR 0124: Platform event taxonomy (platform.security.* events)
- ADR 0126: Observation-to-action closure loop (CRITICAL findings trigger triage)
- ADR 0133: Portal authentication by default (auth bypass check validates enforcement)
- ADR 0136: HTTP security headers hardening (header check validates deployment)
- ADR 0137: Robots and crawl policy (robots.txt check validates deployment)
- ADR 0139: Subdomain exposure audit (DNS-level; this ADR covers the HTTP surface)
- ADR 0140: Grafana public access hardening (anonymous access check validates enforcement)
