# SSL Certificate Monitoring System — Complete Setup Guide

## Overview

This comprehensive certificate monitoring system provides:

1. **Quick diagnostics** — Check all 53 domains for certificate validity in seconds
2. **Automatic monitoring** — Uptime Kuma monitors track expiration and validity
3. **Automatic alerts** — Slack/email notifications for issues
4. **Automated remediation** — Playbooks to fix certificate problems
5. **Audit trail** — JSON reports of all certificate validation runs

## Files Added

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/certificate_validator.py` | Check all domains for SSL certificate validity |
| `scripts/add-certificate-monitors-to-uptime-kuma.py` | Populate Uptime Kuma with SSL monitors |

### Playbooks

| Playbook | Purpose |
|----------|---------|
| `playbooks/certificate-validation.yml` | Run comprehensive certificate validation |
| `playbooks/fix-edge-certificate.yml` | Fix missing domains in NGINX edge certificate |

### Documentation

| Document | Purpose |
|----------|---------|
| `docs/runbooks/certificate-monitoring.md` | Detailed runbook for ops |
| `docs/certificate-monitoring-setup.md` | This setup guide |

## Quick Start

### 1. Check All Domains Right Now

```bash
# Check all edge-published domains
python3 scripts/certificate_validator.py --check-all

# Check a specific domain
python3 scripts/certificate_validator.py --fqdn ci.example.com

# Get JSON output for automation
python3 scripts/certificate_validator.py --check-all --json
```

### 2. Fix ci.example.com Certificate Issue

The validator will show: **ci.example.com has certificate hostname mismatch**

**Quick Fix:**
```bash
# Run the edge certificate refresh
make converge-nginx-edge env=production
```

If that doesn't work, run the specialized playbook:
```bash
ansible-playbook playbooks/fix-edge-certificate.yml
```

### 3. Set Up Automatic Monitoring in Uptime Kuma

```bash
# Get your API key from https://uptime.example.com/settings/api-keys

# Create monitors for all domains (requires API key)
python3 scripts/add-certificate-monitors-to-uptime-kuma.py \
    --base-url https://uptime.example.com \
    --api-key <your-api-key> \
    --config config/subdomain-catalog.json

# Dry-run first to see what would be created
python3 scripts/add-certificate-monitors-to-uptime-kuma.py \
    --base-url https://uptime.example.com \
    --api-key <your-api-key> \
    --dry-run
```

## What the Validator Checks

For each domain, the validator verifies:

1. **Connectivity** — Can connect to the target host on port 443
2. **Certificate Validity** — Certificate is properly signed and valid
3. **Hostname Match** — Certificate CN/SANs match the domain name
4. **Expiration** — Certificate hasn't expired
5. **Expiration Warning** — Alerts if expiring within 30 days

## Output Example

```
================================================================================
SSL CERTIFICATE VALIDATION REPORT
================================================================================

Total Domains: 53
✓ Valid: 34
⚠ Expiring Soon (< 30 days): 0
✗ Expired: 0
✗ Certificate Mismatch: 2
✗ Connection Failed: 17

ISSUES FOUND:
----------------

[CERT_MISMATCH] ci.example.com (woodpecker)
  Target: 203.0.113.1:443
  CN: lv3-edge
  SANs: *.example.com, example.com, ...
  Error: Certificate CN=lv3-edge, SANs=[...], but domain is ci.example.com

  REMEDIATION:
  - The certificate for ci.example.com does not match.
  - Check that all subdomains are included in the certificate request.
  - Run: make converge-nginx-edge env=production
```

## Understanding the Results

### ✓ Valid (Green)
Certificate is valid and not expiring soon. No action needed.

### ⚠ Expiring Soon (Yellow)
Certificate expires in < 30 days. Schedule renewal:
```bash
make converge-nginx-edge env=production
```

### ✗ Expired (Red)
Certificate has expired. **CRITICAL** — fix immediately:
```bash
make converge-nginx-edge env=production
```

### ✗ Cert Mismatch (Red)
Certificate doesn't cover this domain. Causes:
- Domain not included in certificate request
- Service not configured in platform topology
- Subdomain catalog incorrect

**Fix:**
1. Verify `config/subdomain-catalog.json` has `"exposure": "edge-published"`
2. Ensure service has proper edge config in `playbooks/services/<service>.yml`
3. Run: `make converge-nginx-edge env=production`

### ✗ Connection Failed (Red)
Can't connect to the host. Usually means:
- Host is offline
- Port is wrong
- Firewall blocking access
- Service not deployed

## Integration with CI/CD

### Run Before Deployments

Add to your pre-deploy checks:
```bash
# Fail if any certificate issues
python3 scripts/certificate_validator.py --check-all

# Exit code 0 = all valid, exit code 1 = issues found
```

### Schedule Periodic Checks

Add to crontab:
```bash
# Daily certificate check at 2 AM
0 2 * * * cd /path/to/repo && python3 scripts/certificate_validator.py --check-all > /tmp/cert-check.log 2>&1

# Weekly detailed report
0 3 * * 0 cd /path/to/repo && python3 scripts/certificate_validator.py --check-all --json > /tmp/cert-check-$(date +%Y%m%d).json
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'requests'"

Required for the Uptime Kuma script only:
```bash
pip install requests
```

The main validator.py script only uses Python stdlib.

### "HSTS error: net::ERR_CERT_COMMON_NAME_INVALID"

This means the certificate was invalid for that domain at some point, and HSTS (HTTP Strict Transport Security) is preventing retry.

**Clear HSTS cache:**
1. Chrome: Settings → Privacy → Clear browsing data → Cookies → Clear
2. Or use: `chrome://net-internals/#hsts` (type domain, click "Delete")

Then re-test.

### Validator hangs on a domain

Domain might be unreachable or firewalled. You can timeout:
```bash
python3 scripts/certificate_validator.py --timeout 5 --fqdn domain.example.com
```

## Real-World Scenarios

### Scenario 1: Bulk Check Before Major Deployment

```bash
# 1. Validate all certificates
python3 scripts/certificate_validator.py --check-all

# 2. Check output for critical issues
# 3. If any "EXPIRED" — stop and fix immediately
# 4. If any "CERT_MISMATCH" — check subdomain-catalog.json
# 5. Proceed with deployment
```

### Scenario 2: Certificate About to Expire in 7 Days

```bash
# 1. See warning: "analytics.example.com expires in 7 days"
python3 scripts/certificate_validator.py --check-all

# 2. Trigger renewal immediately
make converge-nginx-edge env=production

# 3. Verify renewal succeeded
python3 scripts/certificate_validator.py --fqdn analytics.example.com
# Should show: "✓ Valid" instead of "⚠ Expiring Soon"
```

### Scenario 3: New Service with New Subdomain

```bash
# 1. Add to subdomain-catalog.json
# {
#   "fqdn": "my-service.example.com",
#   "service_id": "my-service",
#   "exposure": "edge-published",
#   "target": "203.0.113.1",
#   "target_port": 443,
#   "tls": { "provider": "letsencrypt", "auto_renew": true }
# }

# 2. Deploy the service
make converge-<service> env=production

# 3. Refresh nginx edge with new domain
make converge-nginx-edge env=production

# 4. Verify the certificate includes the new domain
python3 scripts/certificate_validator.py --fqdn my-service.example.com
# Should show: "✓ Valid"
```

## Automated Monitoring Dashboard

Once monitors are added to Uptime Kuma:

1. Visit https://uptime.example.com
2. Look for monitors tagged `ssl-certificate`
3. Each shows:
   - Current response time
   - Uptime percentage
   - Last check status
   - **Certificate expiration date** (30 days warning)

## Related Runbooks

- [Certificate Monitoring Runbook](./runbooks/certificate-monitoring.md)
- [Configure Edge Publication](./runbooks/configure-edge-publication.md)
- [Renew Certificate](./runbooks/renew-certificate.yaml)

## Architecture

```
┌─────────────────────────────────────────────────┐
│ certificate_validator.py                        │
│ - Checks all 53 edge domains                    │
│ - Validates CN/SAN matches                      │
│ - Checks expiration dates                       │
│ - Reports detailed issues                       │
└────────────┬────────────────────────────────────┘
             │
             ├──→ Immediate issues fixed by
             │    certificate-validation.yml
             │    (run as part of converge)
             │
             └──→ Uptime Kuma monitors
                  added by:
                  add-certificate-monitors-to-uptime-kuma.py
                  - Hourly SSL checks
                  - 30-day warning
                  - Slack/email alerts
```

## Support

For issues:

1. Check the detailed error message from validator
2. Read the REMEDIATION section
3. Follow the suggested fix
4. If still stuck, check logs:
   - Certbot: `sudo journalctl -u certbot -f`
   - Nginx: `sudo tail -f /var/log/nginx/error.log | grep ssl`
5. Create a Git issue with:
   - Output from `certificate_validator.py --check-all`
   - Output from the remediation attempt
