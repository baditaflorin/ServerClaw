# Certificate Monitoring System — Quick Reference

This document provides quick reference for the new SSL certificate monitoring system.

## Problem Fixed

**ci.lv3.org Error:** `net::ERR_CERT_COMMON_NAME_INVALID`

**Root Cause:** The NGINX edge certificate doesn't include ci.lv3.org (and bi.lv3.org) in its Subject Alternative Names.

**Solution:** New monitoring system + automated certificate validation + automatic fixes.

---

## System Components

### 1. Certificate Validator (`scripts/certificate_validator.py`)

Checks all 53 edge-published domains for:
- Connectivity
- Certificate validity
- Hostname/domain match (CN and SANs)
- Expiration dates
- Detailed remediation steps

**Quick Usage:**
```bash
# Check all domains
python3 scripts/certificate_validator.py --check-all

# Check one domain
python3 scripts/certificate_validator.py --fqdn ci.lv3.org

# JSON output
python3 scripts/certificate_validator.py --check-all --json
```

### 2. Uptime Kuma Integration (`scripts/add-certificate-monitors-to-uptime-kuma.py`)

Automatically adds SSL certificate monitors to your Uptime Kuma dashboard.

Each monitor:
- Checks certificate validity hourly
- Alerts when expiring < 30 days
- Tracks certificate details in dashboard

**Usage:**
```bash
# Get API key from https://uptime.lv3.org/settings/api-keys
# Then:
python3 scripts/add-certificate-monitors-to-uptime-kuma.py \
    --base-url https://uptime.lv3.org \
    --api-key <api-key> \
    --config config/subdomain-catalog.json
```

### 3. Validation Playbook (`playbooks/certificate-validation.yml`)

Ansible playbook that runs certificate validation and reports:
- Count of valid/expiring/expired/mismatched domains
- Detailed error messages
- Saves JSON report to `build/certificate-validation-report.json`

**Usage:**
```bash
ansible-playbook playbooks/certificate-validation.yml
```

### 4. Certificate Fix Playbook (`playbooks/fix-edge-certificate.yml`)

Automatically fixes missing domains in the NGINX edge certificate.

**Usage:**
```bash
ansible-playbook playbooks/fix-edge-certificate.yml
# Or via make target
make converge-nginx-edge env=production
```

---

## Immediate Fix for ci.lv3.org

### Step 1: Verify the Issue

```bash
python3 scripts/certificate_validator.py --fqdn ci.lv3.org
```

Expected output:
```
[CERT_MISMATCH] ci.lv3.org (woodpecker)
  Error: Certificate CN=lv3-edge, SANs=[...], but domain is ci.lv3.org

  REMEDIATION:
  - The certificate for ci.lv3.org does not match.
  - Run: make converge-nginx-edge env=production
```

### Step 2: Refresh the Certificate

**Easiest method:**
```bash
make converge-nginx-edge env=production
```

**Or manually:**
```bash
ansible-playbook playbooks/fix-edge-certificate.yml
```

### Step 3: Verify Fix

```bash
python3 scripts/certificate_validator.py --check-all | grep ci.lv3.org
```

Should show: `✓ Valid`

---

## Check All Domains

```bash
python3 scripts/certificate_validator.py --check-all
```

This will:
1. Check all 53 edge-published domains
2. Count valid/invalid/expiring
3. List each issue with remediation steps
4. Exit with code 0 (valid) or 1 (issues)

---

## Understand the Results

### ✓ Valid (Green)
Certificate is valid and not expiring soon. No action.

### ⚠ Expiring Soon (Yellow)
Certificate expires < 30 days.
```bash
make converge-nginx-edge env=production
```

### ✗ Expired (Red)
**CRITICAL** — Certificate is expired!
```bash
make converge-nginx-edge env=production
```

### ✗ Cert Mismatch (Red)
Domain not in certificate.
1. Check `config/subdomain-catalog.json` has `"exposure": "edge-published"`
2. Run: `make converge-nginx-edge env=production`

---

## Set Up Automatic Monitoring

### In Uptime Kuma

```bash
# Get API key from https://uptime.lv3.org/settings/api-keys

python3 scripts/add-certificate-monitors-to-uptime-kuma.py \
    --base-url https://uptime.lv3.org \
    --api-key <api-key>

# Dry-run first to see what would be created:
python3 scripts/add-certificate-monitors-to-uptime-kuma.py \
    --base-url https://uptime.lv3.org \
    --api-key <api-key> \
    --dry-run
```

Then view monitors at https://uptime.lv3.org (tag: "ssl-certificate")

### In Cron

```bash
# Add to crontab
0 2 * * * cd /path/to/repo && python3 scripts/certificate_validator.py --check-all > /tmp/cert-check.log 2>&1
```

---

## Files Added

```
scripts/
  ├── certificate_validator.py          ← Check all domains
  └── add-certificate-monitors-to-uptime-kuma.py  ← Add Uptime Kuma monitors

playbooks/
  ├── certificate-validation.yml        ← Ansible validation playbook
  └── fix-edge-certificate.yml          ← Auto-fix missing domains

docs/
  ├── runbooks/certificate-monitoring.md        ← Detailed ops runbook
  ├── certificate-monitoring-setup.md           ← Complete setup guide
  └── CERTIFICATE-MONITORING.md (this file)     ← Quick reference

build/
  └── certificate-validation-report.json        ← Generated report
```

---

## Troubleshooting

### Script Error: ModuleNotFoundError: 'requests'

Only needed for Uptime Kuma script:
```bash
pip install requests
```

The main validator only uses Python stdlib (ssl, socket, datetime, etc).

### HSTS Error When Testing in Browser

Chrome cached "HSTS: reject all certs for this domain"

**Clear HSTS cache:**
1. `chrome://net-internals/#hsts`
2. Search for domain
3. Click "Delete"

### Validator Hangs on a Domain

Domain unreachable. Use timeout:
```bash
python3 scripts/certificate_validator.py --timeout 5 --fqdn domain.lv3.org
```

---

## Related Documentation

- [Certificate Monitoring Runbook](docs/runbooks/certificate-monitoring.md) — Detailed ops guide
- [Complete Setup Guide](docs/certificate-monitoring-setup.md) — Full integration guide
- [ADR 0249: HTTPS/TLS Assurance](docs/adr/0249.md) — Architecture decision

---

## Key Takeaways

1. **All 53 domains are now monitored** — No more surprise cert failures
2. **Automatic validation** — Run anytime to check status
3. **Uptime Kuma integration** — Visual dashboard with alerts
4. **Automated remediation** — One command fixes most issues
5. **Detailed diagnostics** — Clear error messages and next steps

**Start now:**
```bash
# 1. Check current status
python3 scripts/certificate_validator.py --check-all

# 2. Fix any issues (especially ci.lv3.org)
make converge-nginx-edge env=production

# 3. Add automatic monitoring
python3 scripts/add-certificate-monitors-to-uptime-kuma.py \
    --base-url https://uptime.lv3.org \
    --api-key <api-key>
```

---

Generated: 2026-04-06
