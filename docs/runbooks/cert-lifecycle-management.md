# Runbook: Certificate Lifecycle Management (ADR 0414)

This runbook covers programmatic cert and subdomain operations via
`scripts/cert_lifecycle_manager.py`. For emergency manual renewal, see
`docs/runbooks/cert-expired.md`.

---

## Quick Reference

```bash
# See all subdomains and their cert status
python3 scripts/cert_lifecycle_manager.py list

# Check one domain
python3 scripts/cert_lifecycle_manager.py status --domain service.example.com

# Add new subdomain (dry-run first)
python3 scripts/cert_lifecycle_manager.py create-subdomain \
  --domain newservice.example.com --target 10.10.10.92 --target-port 3001

# Add new subdomain (apply)
python3 scripts/cert_lifecycle_manager.py create-subdomain \
  --domain newservice.example.com --target 10.10.10.92 --target-port 3001 --apply

# Delete subdomain
python3 scripts/cert_lifecycle_manager.py delete-subdomain \
  --domain oldservice.example.com --apply

# Force-renew all certs
python3 scripts/cert_lifecycle_manager.py renew --apply

# Auto-repair all cert mismatches (what the cron runs)
python3 scripts/cert_lifecycle_manager.py sync-missing --apply
```

---

## Pre-Push Gate: Bypassing Cert Validation

If the pre-push hook reports `cert_mismatch` entries and you need to push now:

```bash
SKIP_CERT_VALIDATION=1 \
  GATE_BYPASS_REASON_CODE=cert-mismatch-pending-converge \
  GATE_BYPASS_DETAIL="<describe the situation>" \
  git push origin <branch>
```

**Requirements:**
- `GATE_BYPASS_REASON_CODE` must be set (bypass is logged; empty code = audit gap)
- You must follow up within one working day with `make converge-nginx-edge env=production`

**Do NOT use `git push --no-verify`** — this skips all gates (ADR validation, NATS
topics, remote gate) not just cert validation.

---

## Forks Without Hetzner DNS API

If you forked this platform and do not have Hetzner DNS API credentials, you cannot
use certbot DNS-01 challenge for wildcard certs. Options:

### Option A: Skip cert validation entirely
Add to `.local/identity.yml`:
```yaml
platform_cert_validation_mode: skip
```

The pre-push gate will skip cert validation. The `cert_lifecycle_manager.py` commands
will run in skip mode for validation steps but will still update catalogs.

### Option B: Warn mode (validation runs but doesn't block)
```yaml
platform_cert_validation_mode: warn
```

cert_mismatch entries print warnings but do not fail the gate.

### Option C: Use HTTP-01 challenge
If your certbot setup supports HTTP-01 (instead of DNS-01), edit
`collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/tasks/main.yml`
to use `--preferred-challenges http` in the certbot invocation.

---

## Adding a New Subdomain (Full Lifecycle)

1. **Dry-run first:**
   ```bash
   python3 scripts/cert_lifecycle_manager.py create-subdomain \
     --domain newservice.example.com \
     --target 10.10.10.92 \
     --target-port 3001
   ```
   Review the output — it shows what catalog entries will be written.

2. **Apply:**
   ```bash
   python3 scripts/cert_lifecycle_manager.py create-subdomain \
     --domain newservice.example.com \
     --target 10.10.10.92 \
     --target-port 3001 \
     --apply
   ```
   This writes to `config/subdomain-catalog.json` and `config/certificate-catalog.json`,
   then runs `make converge-nginx-edge env=production`, and verifies the cert.

3. **Verify manually:**
   ```bash
   python3 scripts/certificate_validator.py --fqdn newservice.example.com
   ```

4. **Commit the catalog changes:**
   ```bash
   git add config/subdomain-catalog.json config/certificate-catalog.json
   git commit -m "feat: add newservice.example.com subdomain"
   ```

---

## Removing a Subdomain

1. **Dry-run:**
   ```bash
   python3 scripts/cert_lifecycle_manager.py delete-subdomain \
     --domain oldservice.example.com
   ```

2. **Apply:**
   ```bash
   python3 scripts/cert_lifecycle_manager.py delete-subdomain \
     --domain oldservice.example.com --apply
   ```
   This removes catalog entries and re-runs `converge-nginx-edge` to rebuild the
   SAN cert without the deleted domain. The cert is NOT revoked (cert revocation
   is separate and rarely needed).

3. **Commit:**
   ```bash
   git add config/subdomain-catalog.json config/certificate-catalog.json
   git commit -m "chore: remove oldservice.example.com subdomain"
   ```

---

## Cron Auto-Sync

The cron job runs `sync-missing --apply` daily at 03:00 UTC on the nginx edge host.

**Check cron log:**
```bash
# On the nginx edge host (10.10.10.92):
cat /var/log/cert-sync-$(date +%Y%m%d).json | python3 -m json.tool
```

**Check systemd timer status:**
```bash
systemctl status cert-sync.timer
journalctl -u cert-sync.service --since today
```

**Manual cron trigger:**
```bash
python3 scripts/cert_lifecycle_manager.py sync-missing --apply --json
```

---

## LibreChat Agent Usage

The cert lifecycle manager is exposed as an agent tool in LibreChat
(`chat.example.com`). Invoke the cert agent with natural language:

- "List all subdomains with their cert status"
- "Add a new subdomain metrics.example.com pointing to 10.10.10.92:3001"
- "Check the cert status of grafana.example.com"
- "Renew the cert for ci.example.com"
- "Fix all cert mismatches"

The agent calls `cert_lifecycle_manager.py` with `--json` and presents results
in the chat interface. Mutating operations require explicit confirmation from the
operator in chat before `--apply` is passed.

---

## Troubleshooting

### cert_mismatch in pre-push gate

```
CRITICAL: 16 certificate issue(s):
  - ci.example.com: cert_mismatch
  ...
```

**Immediate fix (push now, repair later):**
```bash
SKIP_CERT_VALIDATION=1 GATE_BYPASS_REASON_CODE=cert-mismatch-pending-converge \
  git push origin <branch>
# Then within 24h:
make converge-nginx-edge env=production
```

**Full fix:**
```bash
python3 scripts/cert_lifecycle_manager.py sync-missing --apply
```

### create-subdomain fails at certbot step

certbot may fail if:
- Hetzner DNS API credentials are missing from `.local/`
- The domain is not within the configured DNS zone
- Rate limits hit (5 certs per domain per week)

Check certbot logs on the nginx edge host:
```bash
journalctl -u certbot --since "1 hour ago"
cat /var/log/letsencrypt/letsencrypt.log | tail -50
```

### sync-missing runs but mismatches remain

Possible causes:
1. certbot DNS-01 challenge failed (DNS propagation delay)
2. nginx reload failed after cert update
3. The mismatch is for an internal service (not reachable from nginx edge)

Manual check:
```bash
openssl s_client -connect 10.10.10.92:443 -servername ci.example.com 2>/dev/null \
  | openssl x509 -noout -text | grep -A2 "Subject Alternative Name"
```
