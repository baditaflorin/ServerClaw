# ADR 0360: OpenBao TLS Cert Lifetime And Renewal Hardening

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: pending
- Implemented In Platform Version: pending
- Implemented On: 2026-04-05
- Date: 2026-04-05

## Context

OpenBao issues its own TLS certificate via Step CA at startup and on a
systemd renewal timer. The certificate is issued with a 24-hour lifetime
(`openbao_tls_certificate_not_after: 24h`). The renewal timer fires every
15 minutes and renews when the certificate is within 6 hours of expiry.

On 2026-04-03 the OpenBao TLS certificate expired because the renewal timer
silently failed. This caused all secret delivery to every platform service to
stop: every Compose service that uses OpenBao-injected secrets via the
`openbao-agent` sidecar pattern could not authenticate to OpenBao, leading to
a broad platform degradation.

Two structural gaps enabled this incident:

1. **No safety margin.** With a 24h cert and a single renewal path (the
   systemd timer), any single missed renewal cycle — whether from a host
   reboot, Step CA unavailability, or timer misconfiguration — causes
   immediate cert expiry. There is zero tolerance for renewal failures.

2. **No monitoring.** OpenBao was absent from the Alertmanager
   `probe_ssl_earliest_cert_expiry` monitoring list. The 14-day warning
   threshold present in the `CertificateExpiringSoon` alert is structurally
   useless for a 24h cert: the cert expires and renews long before 14 days
   have elapsed, so the alert can never fire in time.

## Decision

### 1. Extend the OpenBao TLS certificate lifetime from 24h to 72h

Setting `openbao_tls_certificate_not_after: 72h` keeps the renewal logic
unchanged (renew when within 6h of expiry, timer fires every 15min) while
providing approximately **66 hours of missed-renewal tolerance**. If the
renewal timer fails to run for any reason — host reboot, Step CA downtime,
network partition — operators have more than two full days to detect and
remediate before the cert expires.

### 2. Add OpenBao to the `probe_ssl_earliest_cert_expiry` monitoring service regex

Include `openbao` in the existing `CertificateExpiringSoon` alert so that
cert expiry for the OpenBao endpoint is observable on the same 14-day
warning path as all other platform services.

### 3. Add a tight critical alert for imminent short-lived cert expiry

Add a new `TlsCertificateExpiryCritical` alert that fires when the OpenBao
certificate has fewer than 4 hours remaining. For a 72h cert with a 6h
renew-before window the renewal should complete well before the 4h threshold;
if the alert fires it means the renewal timer has failed and operator
intervention is required immediately.

## Consequences

**Positive**

- A missed renewal cycle no longer causes immediate cert expiry. With 72h
  cert lifetime and a 6h renew-before window, the timer can miss up to
  approximately 66 hours of renewal attempts before expiry.
- OpenBao cert health is now observable via Alertmanager. Any cert expiry
  approaching within 14 days triggers a warning; expiry within 4 hours
  triggers a critical page.
- The critical 4h alert fires early enough to act before services start
  failing: even if the alert takes 5 minutes to fire, operators have ~3h55m
  to run `make converge-openbao` before the cert expires.

**Negative / Trade-offs**

- Extending cert lifetime to 72h increases the window during which a
  compromised private key remains valid before the next rotation. This is
  accepted because the OpenBao TLS cert is issued for an internal mTLS
  endpoint protected by Step CA's root of trust; the primary threat model
  is availability, not key compromise.
- A 72h cert means the cert is renewed less frequently under normal
  conditions (roughly every 66h vs. every 18h). Log-based auditing of
  cert renewal events will show lower frequency.

## Boundaries

- This ADR covers only the OpenBao server TLS certificate lifetime and its
  associated Alertmanager monitoring rules.
- The renewal timer schedule (`*:0/15`) and renew-before window (6h) are
  unchanged.
- Step CA certificate issuance policy and trust chain are unchanged.
- Other services that use short-lived certificates are out of scope for this
  ADR; they should be evaluated separately if they share the same single-path
  renewal risk.

## Related ADRs

- ADR 0043: OpenBao as the platform secrets backend
- ADR 0101: Step CA as the internal certificate authority
- ADR 0165: OpenBao TLS and mTLS endpoint design
- ADR 0231: Cert renewal automation via systemd timers

## References

- Incident 2026-04-03: OpenBao TLS cert expiry causing platform-wide secret delivery failure
