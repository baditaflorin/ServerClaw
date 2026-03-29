# ADR 0249: HTTPS And TLS Assurance Via Blackbox Exporter And testssl.sh

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.82
- Implemented In Platform Version: 0.130.56
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

The platform already rotates certificates and runs public-surface security
scans, but multi-stage assurance still needs a stricter rule:

- a declared HTTPS surface must prove it negotiates correctly
- the certificate chain, hostname, and expiry must be valid for the declared
  audience
- internal, operator-only, and edge-published HTTPS surfaces must all be
  judged, not only the public internet edge

## Decision

We will use **Prometheus Blackbox Exporter** for recurring protocol-level probe
assurance and **testssl.sh** for deeper TLS posture verification.

### Division of responsibility

- Blackbox Exporter proves endpoint reachability, redirect behavior, TLS
  handshake success, and certificate freshness on recurring probes
- `testssl.sh` provides deeper periodic verification for protocol, cipher, and
  certificate regressions

### Scope

- public edge hostnames
- operator-only HTTPS hostnames
- internal service APIs that are explicitly declared as HTTPS-bearing control
  surfaces

## Consequences

**Positive**

- HTTPS stops being assumed from DNS or catalog data alone
- TLS assurance becomes broader than public-edge-only scanning
- certificate problems become visible through recurring probes before expiry
  becomes an outage

**Negative / Trade-offs**

- private HTTPS paths require stage-aware probe execution locations
- deeper TLS scans take longer and should not run as often as lightweight
  blackbox checks

## Boundaries

- This ADR governs transport assurance, not application-level browser behavior.
- Plain HTTP-only internal services remain out of scope unless another ADR
  upgrades them to HTTPS.

## Related ADRs

- ADR 0042: step-ca for SSH and internal TLS
- ADR 0101: Automated certificate lifecycle management
- ADR 0142: Public surface automated security scan
- ADR 0244: Runtime assurance matrix per service and environment

## References

- <https://github.com/prometheus/blackbox_exporter>
- <https://github.com/testssl/testssl.sh>
