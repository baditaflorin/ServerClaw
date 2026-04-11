# ADR 0375: Certificate Validation And Concordance Enforcement

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: TBD (this PR)
- Implemented In Platform Version: TBD (pending merge)
- Date: 2026-04-06

## Context

ADR 0101 (Automated Certificate Lifecycle Management) and ADR 0273 (Public Endpoint Admission Control) require that certificates remain concordant with the DNS catalog and published endpoints. However, the actual *implementation* of this concordance checking is missing.

Recent operational incidents demonstrate the problem:

- ci.example.com, bi.example.com, grist.example.com, paperless.example.com, annotate.example.com, and ntfy.example.com all have **certificate hostname mismatch** errors because they are in `config/subdomain-catalog.json` with `exposure: "edge-published"` but are **missing from the NGINX edge certificate's Subject Alternative Names (SANs)**.

- There is no automated check to detect this mismatch before deployment or before the user encounters a broken site.

- There is no programmatic way to find "which domains are missing from the certificate" without manual investigation.

- The existing `tls_cert_probe.py` (referenced in ADR 0101) does not validate *domain membership in certificates*, only expiration dates.

## Decision

We will implement **certificate validation and concordance enforcement** that:

1. **Validates certificate coverage** — Ensures all `exposure: "edge-published"` domains in `subdomain-catalog.json` are present in their target certificate's SANs
2. **Validates domain/certificate matching** — Ensures each domain's certificate CN/SANs match the domain name (no hostname mismatches)
3. **Detects mismatches programmatically** — Provides scripts to identify issues before deployment
4. **Automates remediation** — Provides playbooks to regenerate certificates with missing domains
5. **Integrates with Uptime Kuma** — Adds automatic hourly SSL validation monitors
6. **Codifies in workflows** — Makes validation part of pre-push checks and CI/CD gates

### 1. Certificate Validator Script

`scripts/certificate_validator.py` — Check all edge-published domains for SSL certificate validity:

```bash
# Check all edge-published domains
python3 scripts/certificate_validator.py --check-all

# Check one domain
python3 scripts/certificate_validator.py --fqdn ci.example.com

# JSON output for automation
python3 scripts/certificate_validator.py --check-all --json
```

**Validates:**
- Connectivity to target host on port 443
- Certificate is properly signed and not self-signed (for edge certificates)
- Certificate CN (Common Name) or SANs include the domain (or wildcard match)
- Certificate has not expired
- Certificate is not expiring within 30 days

**Output:**
- Human-readable summary with remediation steps
- JSON report for CI/CD integration
- Exit code 0 (all valid) or 1 (issues found)

**Implementation:**
```python
def validate_certificate(fqdn: str, target: str, port: int) -> CertValidationResult:
    # 1. Connect to target:port and retrieve certificate
    # 2. Extract CN and SANs
    # 3. Check if fqdn matches CN or SANs (including wildcards)
    # 4. Parse expiration date
    # 5. Report status and remediation steps
```

### 2. Concordance Admission Check

`playbooks/certificate-validation.yml` — Validate all certificates as part of converge workflow:

```bash
ansible-playbook playbooks/certificate-validation.yml
```

This playbook:
- Loads `config/subdomain-catalog.json`
- Filters to `exposure: "edge-published"` or `"edge-static"`
- Runs certificate validator on each domain
- Reports summary (valid/expiring/expired/mismatch/failed)
- Fails if any domain has:
  - Expired certificate (critical)
  - Certificate hostname mismatch (critical)
  - Connection failure (warning)
- Provides detailed remediation steps

### 3. Automated Certificate Remediation

`playbooks/fix-edge-certificate.yml` — Automatically fix missing domains in NGINX edge certificate:

```bash
ansible-playbook playbooks/fix-edge-certificate.yml
```

Or simpler (via existing make target):
```bash
make converge-nginx-edge env=production
```

This playbook:
1. Collects all `exposure: "edge-published"` domains from `subdomain-catalog.json`
2. Retrieves current NGINX edge certificate
3. Compares installed SANs vs. desired domains
4. If missing domains found:
   - Backs up current renewal config
   - Stops NGINX temporarily
   - Forces Let's Encrypt renewal with ALL missing domains included
   - Installs new certificate
   - Restarts NGINX
5. Verifies the fix with certificate validator

### 4. Uptime Kuma Integration

`scripts/add-certificate-monitors-to-uptime-kuma.py` — Automatically add SSL monitoring:

```bash
python3 scripts/add-certificate-monitors-to-uptime-kuma.py \
    --base-url https://uptime.example.com \
    --api-key <api-key>
```

Creates monitors for all `exposure: "edge-published"` domains that:
- Check HTTP status hourly
- Validate SSL certificate validity hourly
- Alert when expiring < 30 days
- Track certificate metadata (expiry, CN, SANs)
- Send notifications to Slack/Discord/email

### 5. Workflow Integration

#### Preflight Validation

Before any nginx-edge deployment, validate all certificates:

```bash
# In deployment workflow
ansible-playbook playbooks/certificate-validation.yml

# Or as pre-deployment check
python3 scripts/certificate_validator.py --check-all
```

#### CI/CD Gate

Can be integrated into pre-push gate or CI pipeline:

```bash
# Exit code 0 = all valid, 1 = issues
python3 scripts/certificate_validator.py --check-all
if [ $? -ne 0 ]; then
  echo "Certificate validation failed"
  exit 1
fi
```

#### Scheduled Validation

Add to cron for periodic checks:

```bash
# Daily certificate validation at 2 AM
0 2 * * * cd /repo && python3 scripts/certificate_validator.py --check-all > /tmp/cert-check.log 2>&1
```

## Implementation

### Files Created

```
scripts/
  ├── certificate_validator.py
  │   └── Check all domains for SSL certificate validity
  └── add-certificate-monitors-to-uptime-kuma.py
      └── Add/update SSL monitors in Uptime Kuma

playbooks/
  ├── certificate-validation.yml
  │   └── Ansible validation playbook (runs validator, reports)
  └── fix-edge-certificate.yml
      └── Auto-fix missing domains in NGINX edge certificate

docs/
  ├── runbooks/certificate-monitoring.md
  │   └── Detailed operational runbook
  ├── certificate-monitoring-setup.md
  │   └── Complete setup and integration guide
  └── CERTIFICATE-MONITORING.md
      └── Quick reference guide
```

### Exit Codes

- `0` — All certificates valid, no issues
- `1` — One or more certificate issues found
- `2` — Script error (file not found, invalid JSON, etc.)

### Data Models

#### Certificate Validation Result

```python
@dataclass
class CertValidationResult:
    fqdn: str                              # Domain being validated
    target: str                            # IP/hostname to connect to
    target_port: int                       # Port (usually 443)
    status: CertStatus                     # valid, expired, expiring_soon, cert_mismatch, connection_failed
    common_name: Optional[str]             # Certificate CN
    subject_alt_names: Optional[List[str]] # Certificate SANs
    not_before: Optional[str]              # Certificate start date
    not_after: Optional[str]               # Certificate expiry date
    days_until_expiry: Optional[int]       # Days remaining (negative = expired)
    error_message: Optional[str]           # Error details
    service_id: Optional[str]              # Service from catalog
```

#### JSON Report

```json
[
  {
    "fqdn": "ci.example.com",
    "service": "woodpecker",
    "status": "valid",
    "cn": "lv3-edge",
    "sans": ["*.example.com", "example.com", ...],
    "expires": "Aug 15 00:00:00 2026 GMT",
    "days_until_expiry": 131,
    "error": null
  }
]
```

## Consequences

**Positive**

- Certificate mismatches are detected programmatically before deployment
- Subdomain-catalog.json ↔ certificate concordance is enforced
- Automated remediation prevents manual certificate renewal errors
- Uptime Kuma integration provides visual monitoring dashboard
- Clear audit trail of all certificate validation runs
- Self-documenting — the validator output explains what went wrong and how to fix it

**Negative / Trade-offs**

- Requires Hetzner DNS API credentials for certificate renewal (already required by ADR 0021)
- Certificate validation adds a few seconds to deployment pipelines
- Some internal services (database.example.com, vault.example.com) use self-signed certs and will appear as "failed" (expected behavior — not all domains use edge certificates)

**Risk Mitigation**

- Validator only *reports* issues, does not auto-fix without explicit playbook invocation
- Certificate renewal is atomic — old certificate remains if renewal fails
- Dry-run mode available for Uptime Kuma script to preview what would be created

## Scenarios

### Scenario 1: New Edge-Published Service

1. Add service to `config/subdomain-catalog.json` with `exposure: "edge-published"`
2. Deploy service playbook
3. Run `make converge-nginx-edge env=production` (regenerates cert with new domain)
4. Run `python3 scripts/certificate_validator.py --fqdn my-service.example.com`
5. Should show: `✓ Valid`

### Scenario 2: Certificate Hostname Mismatch Found

1. Run `python3 scripts/certificate_validator.py --check-all`
2. Output shows: `[CERT_MISMATCH] ci.example.com — hostname mismatch`
3. Run `make converge-nginx-edge env=production`
4. Run validator again — should now show `✓ Valid`

### Scenario 3: Certificate Expiring Soon

1. Uptime Kuma alert: "ci.example.com certificate expires in 14 days"
2. Run `make converge-nginx-edge env=production` (certbot renews automatically)
3. Wait for NGINX reload completion
4. Uptime Kuma shows updated expiry date

## Alternatives Considered

- **Manual validation before each deployment** — Error-prone, inconsistent, requires operator memory
- **Validation only in pre-push gate** — Doesn't catch issues until push time; blocks merges unnecessarily
- **Standalone monitoring tool** — Requires separate tool stack; Uptime Kuma already exists
- **Hardcoded domain list** — Requires manual sync with subdomain-catalog.json; defeats purpose of catalog

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge (declares edge-published domains)
- ADR 0101: Automated certificate lifecycle management (describes renewal automation)
- ADR 0273: Public endpoint admission control (requires certificate concordance)
- ADR 0252: Route and DNS publication assertion ledger (publication truth)
- ADR 0015: LV3.org DNS and subdomain model (domain catalog structure)

## Documentation

Operators should refer to:

1. `docs/certificate-monitoring-setup.md` — Full integration guide with examples
2. `docs/runbooks/certificate-monitoring.md` — Step-by-step operational runbook
3. `CERTIFICATE-MONITORING.md` — Quick reference for common tasks
4. Script `--help` output — Full option documentation

## Future Enhancements

- Integration with AlertManager for certificate expiry alerts
- Automated certificate repair via pre-push gate validation
- Certificate transparency log validation (CT logs)
- Support for multi-SAN certificate planning in subdomain-catalog.json
- Integration with GitOps workflow for automatic remediation PRs
