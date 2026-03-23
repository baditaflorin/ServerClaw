# ADR 0101: Automated Certificate Lifecycle Management

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-23

## Context

step-ca (ADR 0042) is provisioned and issues short-lived TLS certificates for internal services and SSH certificates for operators. The ADR describes the issuance model but does not define the **renewal lifecycle**: who is responsible for renewing each certificate, when renewal is triggered, how failures are detected, and what happens if a certificate expires.

Certificate expiry is a notorious operational failure mode: it is predictable, visible in advance, and yet consistently causes production outages. The reason is always the same — renewal was manual, the operator forgot, and the only alert was the service going down.

The platform currently has:
- step-ca issuing certificates with a configurable default lifetime (90 days)
- No automated renewal mechanism for any service
- Drift detection (ADR 0091) that checks certificate expiry as one drift source
- No alert routing (ADR 0097) that escalates certificate warnings to action

The drift detection catches expiry within 7–14 days, but catching a problem 7 days before expiry is not the same as preventing it. Renewal must be automated so that expiry never occurs under normal circumstances.

## Decision

We will implement a **three-layer certificate lifecycle** covering issuance, automated renewal, and expiry alerting, using `step-ca`'s ACME provisioner and the `step` agent for renewal, with health probe integration to verify certificate validity.

### Layer 1: Short-lived certificates with `step` renewal agent

Every service that holds a TLS certificate is configured to run `step ca renew` in daemon mode via a systemd timer or a sidecar container. The `step` agent renews the certificate when it reaches 2/3 of its lifetime (configurable) without any operator involvement.

**For VM-hosted services** (step-ca, OpenBao):

```ini
# /etc/systemd/system/step-renew-openbao.timer
[Unit]
Description=Renew TLS certificate for OpenBao

[Timer]
OnCalendar=*:0/5  # check every 5 minutes
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
```

```bash
# /usr/local/bin/renew-openbao-cert.sh (Ansible-templated)
#!/usr/bin/env bash
step ca renew \
  --ca-url https://ca.internal.lv3:9443 \
  --root /etc/step-ca/certs/root_ca.crt \
  --force-term-on-change \
  /etc/ssl/openbao/cert.pem \
  /etc/ssl/openbao/key.pem \
  && systemctl reload openbao
```

The `--force-term-on-change` flag causes `step ca renew` to exit with a non-zero code if the certificate chain changed, which triggers the `&& systemctl reload openbao` to apply the new certificate without a full restart.

**For Docker Compose services** (Keycloak, Windmill, NetBox, Mattermost):

A shared `cert-renewer` sidecar container runs in each Compose stack:

```yaml
cert-renewer:
  image: smallstep/step-ca:latest
  entrypoint: >
    step ca renew
      --daemon
      --ca-url https://ca.internal.lv3:9443
      --root /certs/root_ca.crt
      --exec "kill -HUP $(cat /var/run/nginx.pid)"
      /certs/service.crt /certs/service.key
  volumes:
    - cert-volume:/certs
  restart: unless-stopped
```

The `--daemon` mode runs continuously, sleeping between renewal checks. The `--exec` command reloads the consuming service when a new certificate is issued.

### Layer 2: Certificate validity health probe

The health probe contracts (ADR 0064) are extended to include a TLS certificate validity check for every service with a public or internal TLS endpoint:

```python
# scripts/tls_cert_probe.py — run by the health probe scheduler
def probe_cert_validity(host: str, port: int, days_warn: int = 21, days_critical: int = 7) -> ProbeResult:
    cert = ssl.get_server_certificate((host, port))
    expiry = parse_cert_expiry(cert)
    days_remaining = (expiry - datetime.utcnow()).days

    if days_remaining < days_critical:
        return ProbeResult.CRITICAL(f"TLS cert expires in {days_remaining} days")
    elif days_remaining < days_warn:
        return ProbeResult.WARN(f"TLS cert expires in {days_remaining} days")
    return ProbeResult.OK(f"TLS cert valid for {days_remaining} days")
```

This probe runs on the same schedule as the other health probes (every 5 minutes) and feeds into:
- Grafana alert rules (via Prometheus metrics from Telegraf)
- SLO burn rate tracking (ADR 0096) — a critical cert failure is an SLO event
- Drift detection (ADR 0091) — cert drift is a `critical` drift event

### Layer 3: Certificate inventory

A `config/certificate-catalog.json` tracks every certificate issued by step-ca:

```json
{
  "certificates": [
    {
      "id": "openbao-internal",
      "service": "openbao",
      "cn": "openbao.internal.lv3",
      "issuer": "step-ca",
      "renewal_agent": "systemd-timer",
      "probe_host": "openbao",
      "probe_port": 8200,
      "lifetime_days": 90,
      "renew_at_percent": 66
    },
    {
      "id": "keycloak-internal",
      "service": "keycloak",
      "cn": "sso.lv3.org",
      "issuer": "lets-encrypt",
      "renewal_agent": "certbot-acme",
      "probe_host": "sso.lv3.org",
      "probe_port": 443,
      "lifetime_days": 90,
      "renew_at_percent": 66
    }
  ]
}
```

This catalog is the source of truth for:
- Generating systemd timers and sidecar renewal configurations (Ansible)
- Populating the health probe schedule
- The docs site reference page (ADR 0094) — which certificates exist and who manages them

### Let's Encrypt certificates (external services)

For `sso.lv3.org`, `grafana.lv3.org`, `ops.lv3.org`, and other edge-published subdomains, certificates are issued by Let's Encrypt via DNS-01 challenge (already implemented per ADR 0021). Certbot is configured with a `--deploy-hook` that reloads nginx on the edge VM when a certificate is renewed. The same TLS probe covers these certificates.

### Alert routing for certificate events

Using the alerting model from ADR 0097:

| Condition | Severity | Destination |
|---|---|---|
| Certificate expiry in < 21 days | `warning` | Mattermost `#platform-alerts` |
| Certificate expiry in < 7 days | `critical` | Ntfy (phone) + Mattermost `#platform-alerts-critical` |
| Renewal agent failed (cert not renewed after 80% lifetime) | `critical` | Ntfy + Mattermost |
| Unexpected issuer (not step-ca or Let's Encrypt) | `warning` | Mattermost |

### Rotation runbook

When automated renewal fails (step-ca unreachable, certificate store corrupted), the manual rotation runbook in the docs site (ADR 0094) provides:

```bash
# Emergency manual certificate renewal
step ca certificate \
  --ca-url https://ca.internal.lv3:9443 \
  --root /etc/step-ca/certs/root_ca.crt \
  "openbao.internal.lv3" \
  /etc/ssl/openbao/cert.pem \
  /etc/ssl/openbao/key.pem
systemctl reload openbao
```

## Consequences

**Positive**
- Certificate expiry becomes an infrastructure-monitored metric, not a calendar reminder; the drift toward "certificates expire in production" is eliminated
- The cert-renewer sidecar pattern is reusable; every new Compose service added to the platform inherits automated renewal by including the sidecar
- The certificate catalog provides a complete inventory of every certificate in the platform — essential for incident response and compliance

**Negative / Trade-offs**
- The cert-renewer sidecar adds one container to every Compose stack; small resource overhead (~10 MB RAM) multiplied across stacks
- step-ca is now a hard runtime dependency for all internal services (it already was at issuance time; now it is also required at renewal time every 60 days); if step-ca is down for more than 60 days, certificates will expire — the step-ca SLO must be high
- The `--exec "kill -HUP"` approach for Compose services requires that the consuming service supports SIGHUP for cert reload; services that require full restart on cert change (some Java services) need a different approach

## Alternatives Considered

- **Manual certificate renewal on a calendar**: the current de facto approach; provably insufficient — calendar items get missed
- **Cert-manager (Kubernetes-native)**: excellent for Kubernetes environments; not applicable to Compose/VM deployments
- **Caddy as TLS terminator for all services**: Caddy manages its own certificates via ACME; would require routing all TLS through a Caddy reverse proxy; introduces a routing dependency for services that currently terminate their own TLS

## Related ADRs

- ADR 0042: step-ca (the CA that issues internal certificates)
- ADR 0047: Short-lived credentials and mTLS (this ADR manages the mTLS certificate lifecycle)
- ADR 0064: Health probe contracts (TLS validity probe is added here)
- ADR 0091: Continuous drift detection (certificate drift is a drift source)
- ADR 0096: SLO definitions (cert expiry events are SLO-affecting)
- ADR 0097: Alerting routing (certificate alerts route through this model)
