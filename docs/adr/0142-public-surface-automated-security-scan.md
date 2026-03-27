# ADR 0142: Public Surface Automated Security Scan

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.129.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The platform already has preventive security controls on its public HTTP or HTTPS surface, but it lacked a repo-managed detective control that validates those controls from the outside on a recurring basis.

That left several public-surface regressions easy to miss:

- a service could lose one or more required HTTP security headers
- an OIDC-protected route could begin serving content before redirecting to Keycloak
- a response could start disclosing application version headers after an upgrade
- the edge could begin accepting weak TLS protocol or cipher combinations
- a redirect flow could pick up an open redirect weakness

The existing ADR 0102 security-posture workflow covers host hardening drift and runtime image CVEs. It does not test what an unauthenticated external user can actually observe on `lv3.org` and the published subdomains.

## Decision

We will run a repo-managed weekly public-surface security scan that writes structured receipts under `receipts/security-scan/` and publishes summary plus high or critical findings on the existing `platform.security.*` control-plane lane.

### Scan scope

The scan targets the active public HTTPS hostnames from the canonical subdomain catalog:

- `edge-published` hostnames
- `informational-only` HTTPS hostnames
- production entries only
- active entries only

The scan excludes:

- private-only hostnames
- non-HTTPS surfaces
- SMTP, submission, and IMAPS ports
- active exploitation templates or fuzzing-style checks

### Implemented checks

The workflow now combines five scan classes:

1. `testssl.sh` against each eligible hostname for TLS protocol, cipher, and certificate regressions
2. an in-repo HTTP header probe for the required external security headers
3. an unauthenticated auth-bypass probe for OIDC-protected public surfaces
4. a version-disclosure probe for response headers such as `X-Powered-By`, `X-*-Version`, and versioned `Server` values
5. `nuclei` redirect or misconfiguration templates against `https://lv3.org`

### Execution model

The repository now ships:

- `scripts/public_surface_scan.py` as the controller-side entrypoint
- `make public-surface-security-scan ENV=production` as the operator-facing command
- `config/windmill/scripts/weekly-security-scan.py` as the Windmill wrapper
- `config/public-surface-scan-policy.json` as the scan policy for required headers, auth expectations, version-header rules, and nuclei scope

The scanner pulls the current official `testssl.sh` and `nuclei` container images at run time unless explicitly told not to, mirroring the repo's existing diagnostic workflow pattern.

### Findings and outputs

Each run writes:

- a timestamped receipt in `receipts/security-scan/`
- raw tool artifacts under `.local/public-surface-scan/<scan_id>/`
- summary and high or critical finding events on `platform.security.*` when NATS publication is enabled

Severity handling:

- CRITICAL: included in the receipt, emitted as `platform.security.critical-finding`, and forwarded to GlitchTip when configured
- HIGH: included in the receipt and emitted as `platform.security.high-finding`
- MEDIUM or LOW: included in the receipt and Mattermost summary only

## Consequences

### Positive

- The platform now has a repo-managed external verification path for its public HTTP or HTTPS controls.
- Operators can review historical receipts instead of relying on ad hoc manual checks.
- The security findings pipeline now covers both internal posture drift and public-surface regressions.

### Negative

- `testssl.sh` and `nuclei` increase scan duration compared with header-only checks.
- The first production run from Windmill still requires apply from `main`; this ADR only claims repository implementation today.
- Public-surface scans generate expected access-log noise on the edge.

## Boundaries

- This ADR covers unauthenticated public HTTP or HTTPS validation only.
- It does not introduce active exploitation, fuzzing, or authenticated penetration testing.
- It does not replace ADR 0102 host and runtime security-posture reporting.

## Related ADRs

- ADR 0044: Windmill for scheduled workflow execution
- ADR 0057: Mattermost for security summaries
- ADR 0061: GlitchTip for critical finding escalation
- ADR 0083: Docker-based check runner and ephemeral tool execution
- ADR 0102: Security posture reporting and benchmark drift
