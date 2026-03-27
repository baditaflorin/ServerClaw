# ADR 0101: Automated Certificate Lifecycle Management

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.6
- Implemented In Platform Version: 0.130.27
- Implemented On: 2026-03-27
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

We will implement a **three-layer certificate lifecycle** covering inventory, automated renewal where this repository actually owns the renewal path, and expiry detection from the same machine-readable contract.

### Layer 1: Renewal automation where current `main` owns the certificate

The current platform topology does **not** terminate TLS inside every Compose stack. Most operator-facing services remain HTTP-only behind the shared NGINX edge certificate or a private Tailscale proxy. The certificate lifecycle therefore distinguishes between:

- repo-managed renewal paths, where the repository renders both the certificate material and the renewal mechanism
- externally managed renewal paths, where the repository inventories the certificate and probes it but does not replace the issuer's own renewal flow

The current repository-managed renewal paths on `main` are OpenBao and Vaultwarden:

- `openbao_runtime` now renders a dedicated systemd timer and service via `lv3.platform.cert_renewal_timer`
- `vaultwarden_runtime` now renders the same timer pattern for the private Vaultwarden HTTPS listener
- both timers reissue short-lived server certificates from step-ca before expiry using the existing `services` provisioner credentials
- both timers only restart their container when the certificate actually changed

For external paths that already renew outside this role:

- the shared NGINX edge bundle remains Certbot-managed on `nginx-lv3`
- the Proxmox manager certificate remains Proxmox ACME-managed on the host
- step-ca's own bootstrap certificate is explicitly inventoried as a special case, not silently ignored
- Portainer and PBS are inventoried and probed even though they still use their own local certificate lifecycle

The repository now also carries a reusable `cert_renewer_sidecar` role for future TLS-owning Compose services, but it is **not** attached to the current HTTP-only control-plane stacks just to satisfy the ADR mechanically.

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

This probe now exists as `scripts/tls_cert_probe.py`, backed by the certificate catalog. It feeds into:
- the platform observation loop via `check-certificate-expiry`
- drift detection via `scripts/tls_cert_drift.py`
- the health-probe contract by way of `tls_certificate_ids` attached to services with HTTPS endpoints
- future alert routing via the committed `config/alertmanager/rules/platform.yml` rule group

### Layer 3: Certificate inventory

A `config/certificate-catalog.json` now tracks every active HTTPS endpoint on current `main`, including:

```json
{
  "certificates": [
    {
      "id": "openbao-proxy",
      "service_id": "openbao",
      "expected_issuer": "step-ca",
      "renewal": {
        "agent": "systemd-step-issue",
        "managed_by_repo": true
      }
    },
    {
      "id": "grafana-edge",
      "service_id": "grafana",
      "expected_issuer": "letsencrypt",
      "renewal": {
        "agent": "certbot-dns-hetzner",
        "managed_by_repo": false
      }
    }
  ]
}
```

This catalog is now the source of truth for:
- the operator-facing TLS probe script
- certificate drift detection
- the OpenBao renewal execution plan generated by `scripts/generate_cert_renewal_config.py`
- health-probe references for services that own HTTPS endpoints

### Let's Encrypt certificates (external services)

For `sso.lv3.org`, `grafana.lv3.org`, `ops.lv3.org`, and other edge-published subdomains, certificates are issued by Let's Encrypt via DNS-01 challenge (already implemented per ADR 0021). Certbot is configured with a `--deploy-hook` that reloads nginx on the edge VM when a certificate is renewed. The same TLS probe covers these certificates.

### Alert routing for certificate events

Using the alerting model from ADR 0097, the repository now carries the certificate alert rule group under `config/alertmanager/rules/platform.yml`:

| Condition | Severity | Destination |
|---|---|---|
| Certificate expiry in < 21 days | `warning` | Mattermost `#platform-alerts` |
| Certificate expiry in < 14 days | `critical` | Ntfy (phone) + Mattermost `#platform-alerts-critical` |
| Renewal agent failed (cert not renewed after 80% lifetime) | `critical` | Ntfy + Mattermost |
| Unexpected issuer (not step-ca or Let's Encrypt) | `warning` | Mattermost |

### Rotation runbook

When automated renewal fails (step-ca unreachable, certificate store corrupted), the repository runbook `docs/runbooks/cert-expired.md` provides:

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

## Implementation Notes

- `config/certificate-catalog.json` is implemented and validated as a canonical data model.
- `scripts/tls_cert_probe.py` is implemented and now backs both drift detection and the observation-loop certificate check.
- `scripts/tls_cert_probe.py` now resolves the shared repository `.local/step-ca` trust root when run from a git worktree, so branch-local live-apply worktrees can validate `step-ca`-issued endpoints without copying controller-local trust state.
- The certificate catalog now supports hour-based warning windows for short-lived certificates, and current `main` uses that path for the 24-hour OpenBao and Vaultwarden certificates so healthy renewal no longer reads as a permanent critical alert.
- `config/health-probe-catalog.json` now links HTTPS-owning services to the certificate catalog through `tls_certificate_ids`.
- `lv3.platform.cert_renewal_timer` is implemented and is used by both `openbao_runtime` and `vaultwarden_runtime` to keep their private proxy certificates fresh.
- `lv3.platform.cert_renewer_sidecar` is implemented as the future reusable path for TLS-owning Compose stacks, but current `main` intentionally does not force it into HTTP-only stacks.
- `config/alertmanager/rules/platform.yml` now carries the repo-managed certificate expiry alert rule group for the later ADR 0097 runtime.

## Consequences

**Positive**
- Certificate expiry becomes a governed repository surface instead of a private operator memory problem.
- The repository finally distinguishes between certificates it actively renews and certificates it only inventories and probes.
- The certificate catalog provides a complete inventory of the current HTTPS estate — essential for incident response and compliance.

**Negative / Trade-offs**
- OpenBao renewal currently reissues and restarts the container rather than doing an in-process certificate hot reload.
- The shared edge, PBS, Portainer, and step-ca bootstrap certificate remain externally managed; the repo now detects expiry risk there but does not yet remediate it.
- The alert rules are committed before the full Alertmanager runtime exists on current `main`, so the repo contract is ahead of the live alert pipeline.

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
