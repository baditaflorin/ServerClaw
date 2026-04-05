# Certificate Monitoring & Validation Runbook

## Overview

This runbook covers:
- Monitoring SSL certificates for all platform domains
- Detecting certificate mismatches and expiration
- Automatic renewal and alerting
- Troubleshooting certificate issues

## Quick Diagnostics

### Check all domains for certificate validity
```bash
python3 scripts/certificate_validator.py --check-all
```

### Check a specific domain
```bash
python3 scripts/certificate_validator.py --fqdn ci.lv3.org
```

### JSON output for parsing
```bash
python3 scripts/certificate_validator.py --json
```

## Common Issues & Fixes

### Issue: "net::ERR_CERT_COMMON_NAME_INVALID" (e.g., ci.lv3.org)

**Root Cause**: The subdomain is not included in the NGINX edge certificate.

**Fix**:
```bash
# 1. Verify the service is in subdomain-catalog.json
grep '"ci.lv3.org"' config/subdomain-catalog.json

# 2. Force certificate renewal for all edge-published domains
make converge-nginx-edge env=production

# 3. Or manually renew:
ssh -i .local/ssh/bootstrap.id_ed25519 root@<nginx-edge-ip>
sudo certbot renew --force-renewal --cert-name lv3-edge

# 4. Restart nginx
sudo systemctl restart nginx

# 5. Verify the fix
python3 scripts/certificate_validator.py --fqdn ci.lv3.org
```

### Issue: "Certificate expires in X days" (Expiring Soon)

**Root Cause**: Let's Encrypt certificate is nearing expiration.

**Fix**:
```bash
# Option 1: Run the nginx converge playbook (automatic renewal)
make converge-nginx-edge env=production

# Option 2: Manually trigger certbot renewal
ssh -i .local/ssh/bootstrap.id_ed25519 root@<nginx-edge-ip>
sudo certbot renew --force-renewal --cert-name lv3-edge
```

### Issue: "Certificate is expired!"

**Root Cause**: Certificate renewal failed or was not applied.

**CRITICAL - Do immediately**:
```bash
# Run emergency renewal
make converge-nginx-edge env=production

# If the above fails, manually:
ssh -i .local/ssh/bootstrap.id_ed25519 root@<nginx-edge-ip>
sudo certbot renew --force-renewal --cert-name lv3-edge
sudo systemctl restart nginx

# Verify immediately
python3 scripts/certificate_validator.py --check-all
```

### Issue: "Hostname mismatch" (Certificate not valid for domain X)

**Root Cause**: The domain is not included in the certificate's Subject Alternative Names (SANs).

**Causes**:
1. Domain missing from `subdomain-catalog.json` exposure settings
2. Domain marked `edge-published` but not in platform service topology
3. Platform topology filter not picking up the domain

**Fix**:
```bash
# 1. Check subdomain-catalog.json
jq '.subdomains[] | select(.fqdn=="domain.lv3.org")' config/subdomain-catalog.json

# 2. Verify exposure is "edge-published" or "edge-static"
jq '.subdomains[] | select(.fqdn=="domain.lv3.org") | .exposure' config/subdomain-catalog.json

# 3. If not in catalog, add it:
# Edit config/subdomain-catalog.json and add the subdomain entry with:
# - "exposure": "edge-published"
# - Appropriate "tls" config with "auto_renew": true

# 4. Ensure platform_service_topology includes the service with edge publication
# Check playbooks/services/<service-name>.yml for:
# - Service must have a public_hostname
# - Service must have edge: { enabled: true, tls: true }

# 5. Regenerate certificates:
make converge-nginx-edge env=production

# 6. Verify
python3 scripts/certificate_validator.py --fqdn domain.lv3.org
```

## Monitoring Setup

### Uptime Kuma Integration

Certificate expiration is monitored via Uptime Kuma monitors at https://uptime.lv3.org

Checks are configured for:
- HTTP status of each domain
- SSL certificate expiration date (< 30 days = warning)
- TLS/SSL connection validity

### Manual Monitoring

Run validation on a schedule:
```bash
# Via cron (on controller)
0 2 * * * cd /path/to/repo && python3 scripts/certificate_validator.py --check-all > /tmp/cert-check.log 2>&1

# Check results
cat /tmp/cert-check.log
```

### Alerting

Certificate issues can trigger:
1. **Alertmanager alerts** (if integrated)
2. **Email notifications** (via mail-platform)
3. **Uptime Kuma notifications** (Slack, Discord, email)

## Debugging Certificate Generation

### List certificate domains being requested
```bash
# On the edge server
sudo cat /etc/letsencrypt/renewal/lv3-edge.conf | grep domains

# Check what certbot will renew
sudo certbot renew --dry-run --cert-name lv3-edge
```

### Check the actual certificate installed
```bash
# On the edge server
openssl x509 -in /etc/letsencrypt/live/lv3-edge/cert.pem -text -noout | grep -A10 "Subject Alternative Name"

# Check CN (Common Name)
openssl x509 -in /etc/letsencrypt/live/lv3-edge/cert.pem -text -noout | grep "Subject:"
```

### Verify certificate served by NGINX
```bash
openssl s_client -connect 65.108.75.123:443 -servername ci.lv3.org < /dev/null | openssl x509 -text -noout | grep -A10 "Subject Alternative Name"
```

## Certificate Renewal Process

The nginx_edge_publication role handles:

1. **Domain Discovery**: Scans `platform_service_topology` for services with `edge.enabled=true`
2. **Certificate Request**: Collects all domains + aliases for `lv3-edge` cert
3. **ACME Challenge**: Uses DNS-01 with Hetzner DNS plugin
4. **Installation**: Deploys cert to `/etc/letsencrypt/live/lv3-edge/`
5. **Verification**: Validates all domains are covered

### Manual Force Renewal
```bash
# SSH to edge server
ssh -i .local/ssh/bootstrap.id_ed25519 root@<nginx-edge-ip>

# Force renewal (gets new cert even if not near expiry)
sudo certbot renew --force-renewal --cert-name lv3-edge

# Dry-run first to see what would happen
sudo certbot renew --dry-run --cert-name lv3-edge

# Check renewal hooks
ls -la /etc/letsencrypt/renewal-hooks/deploy/
```

## Automation

### CI/CD Integration

Certificate validation runs automatically:
- **Pre-deployment**: Validates all certs before edge converge
- **Post-deployment**: Verifies renewal was successful
- **Periodic**: Daily check via scheduled task

### Playbook: Check Certificates

```bash
make converge-uptime-kuma env=production
```

This also regenerates the platform manifest which may include certificate data.

## Related Documentation

- [ADR 0165: Public Edge Publication](../adr/0165.md)
- [ADR 0249: HTTPS/TLS Assurance](../adr/0249.md)
- [Nginx Edge Configuration](configure-edge-publication.md)
- [Certificate Renewal](renew-certificate.yaml)

## Logs

### Certbot renewal logs
```bash
ssh -i .local/ssh/bootstrap.id_ed25519 root@<nginx-edge-ip>
sudo journalctl -u certbot.timer -f
sudo journalctl -u certbot.service
```

### NGINX error log
```bash
ssh -i .local/ssh/bootstrap.id_ed25519 root@<nginx-edge-ip>
sudo tail -f /var/log/nginx/error.log | grep ssl
```

## Contact

For certificate issues:
- Check Alertmanager at https://alerts.lv3.org
- Review logs in Dozzle at https://logs.lv3.org
- Escalate to platform team via Git issue
