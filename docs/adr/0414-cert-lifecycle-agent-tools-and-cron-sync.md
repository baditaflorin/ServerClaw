# ADR 0414: Certificate Lifecycle Agent Tools and Cron Sync

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: TBD (this PR)
- Implemented In Platform Version: TBD (pending merge)
- Date: 2026-04-14

## Context

ADR 0375 added certificate validation as a pre-push gate but left two problems
unresolved that caused an operator incident:

1. **The `SKIP_CERT_VALIDATION=1` bypass was advertised but never implemented.**
   The pre-push hook printed `SKIP_CERT_VALIDATION=1 git push origin <branch>` as
   the bypass instruction yet never read that env var. Operators had to use
   `git push --no-verify` instead, which skips *all* gate checks, not just cert
   validation. This was discovered when 16 `cert_mismatch` entries blocked a push.
   See ADR 0415 (postmortem) for the full incident analysis.

2. **No programmatic lifecycle management exists for cert+subdomain operations.**
   Adding a new subdomain requires: updating `config/subdomain-catalog.json`,
   updating `config/certificate-catalog.json`, running `make converge-nginx-edge`,
   and manually verifying the cert. There is no single command, no agent-callable
   tool, and no cron-based auto-repair. This raises the barrier for operators and
   makes it impossible to expose subdomain management to an AI agent in LibreChat.

3. **Beginners without Hetzner DNS API credentials have no safe escape hatch.**
   Platforms forked from ServerClaw may not use Hetzner DNS. The validation gate
   has no tiered skip mode — it either validates everything or gets bypassed
   wholesale via `--no-verify`.

### What we have today (the good)

- `scripts/certificate_validator.py` — solid cert check with JSON output
- `config/certificate-catalog.json` + `config/subdomain-catalog.json` — canonical
  catalogs serving as single source of truth
- `playbooks/fix-edge-certificate.yml` — remediation playbook (works, but manual)
- `roles/nginx_edge_publication` — handles multi-domain SAN cert issuance via
  certbot + Hetzner DNS-01 challenge

### What we have today (the bad)

- No single programmatic entry point for lifecycle operations (create/delete/renew/
  revoke a subdomain+cert atomically)
- `SKIP_CERT_VALIDATION=1` silently ignored — operators forced to `--no-verify`
- No cron-based detection of "subdomains with no cert coverage" — mismatches
  accumulate silently until the next push gate catches them
- No agent-callable API for subdomain/cert management from LibreChat or Dify
- No beginner mode for forks without Hetzner DNS API

## Decision

We implement four changes:

### 1. Fix the pre-push bypass (immediately)

`SKIP_CERT_VALIDATION=1` is now read by the pre-push hook and triggers the same
bypass-logging flow as `SKIP_ADR_VALIDATION=1`. Operators must also supply
`GATE_BYPASS_REASON_CODE` for the bypass to be audited properly.

```bash
SKIP_CERT_VALIDATION=1 \
  GATE_BYPASS_REASON_CODE=cert-mismatch-pending-converge \
  git push origin <branch>
```

The bypass is logged via `scripts/log_gate_bypass.py` (same as ADR validation)
so every bypass has an audit trail in the gate-bypass log.

### 2. `scripts/cert_lifecycle_manager.py` — single programmatic entry point

A Python script that handles all cert lifecycle operations against the platform's
nginx edge and Let's Encrypt via the existing Ansible roles. It is:

- **Callable from the shell** by operators
- **Callable from LibreChat** via a Dify/OpenAPI tool definition (agent surface)
- **Callable from cron** for the auto-sync use case

Commands:

| Command | Description |
|---------|-------------|
| `list` | List all subdomains with cert status (valid/mismatch/missing) |
| `create-subdomain` | Add a new subdomain to catalogs + issue cert + deploy nginx config |
| `delete-subdomain` | Remove subdomain from catalogs + revoke/clean cert + remove nginx config |
| `renew` | Force-renew cert for a domain (or all domains) |
| `revoke` | Revoke cert and remove from catalogs |
| `sync-missing` | Detect subdomains with cert_mismatch or no cert coverage, trigger repair |
| `status` | JSON status for a specific FQDN |

Key flags:

| Flag | Purpose |
|------|---------|
| `--apply` | Actually make changes (dry-run is default) |
| `--skip-cert-validation` | Skip the TLS validation step (for forks without Hetzner DNS API) |
| `--domain FQDN` | Target a specific domain |
| `--json` | JSON output for agent tooling |
| `--no-nginx-reload` | Skip nginx reload (useful in batch operations) |

### 3. Cron-based auto-sync

A cron configuration at `config/cert-sync-cron.yaml` defines a scheduled job
that runs `cert_lifecycle_manager.py sync-missing --apply --json` daily. The
Ansible `cert_renewal_timer` role (ADR 0101) is extended to deploy this cron
on the nginx edge host.

The sync job:
1. Calls `certificate_validator.py --check-all --json`
2. Collects all `cert_mismatch` entries
3. For each mismatch: triggers the nginx-edge certbot renewal to add the domain
   to the shared SAN certificate
4. Reloads nginx after all certs are updated
5. Writes a JSON report to `/var/log/cert-sync-$(date +%Y%m%d).json`
6. Exits non-zero if any domain remained uncorrected (triggers systemd failure alert)

### 4. Skip-cert-validation mode for forks

The `cert_lifecycle_manager.py` and `certificate_validator.py` both respect a
new `PLATFORM_CERT_VALIDATION_MODE` variable in `.local/identity.yml`:

```yaml
# .local/identity.yml
platform_domain: example.com
platform_cert_validation_mode: skip   # valid values: enforce (default), skip, warn
```

| Mode | Behaviour |
|------|-----------|
| `enforce` | Default. cert_mismatch = gate failure. |
| `warn` | cert_mismatch = warning in output, gate passes. |
| `skip` | cert_mismatch check skipped entirely (for forks without Hetzner DNS API). |

This is documented in `docs/runbooks/cert-lifecycle-management.md` for
operators forking ServerClaw without Hetzner DNS.

## Agent Surface (LibreChat / Dify)

`cert_lifecycle_manager.py --json` output is structured for tool calling.
The tool definition (in `build/librechat-tools/` after manifest generation)
exposes these operations to the LibreChat agent at `chat.example.com`:

```
POST /tools/cert/list
POST /tools/cert/create-subdomain   { "fqdn": "new.example.com", "target": "10.10.10.92", "target_port": 3000 }
POST /tools/cert/delete-subdomain   { "fqdn": "old.example.com" }
POST /tools/cert/renew              { "fqdn": "service.example.com" }
POST /tools/cert/sync-missing       {}
POST /tools/cert/status             { "fqdn": "service.example.com" }
```

All mutating operations require `--apply` or equivalent confirmation from the
agent conversation context. Dry-run is always the safe default.

## What This Does NOT Do

- Does not manage internal step-ca certificates (ADR 0042 — separate domain)
- Does not handle wildcard certificates (certbot DNS-01 required, not HTTP-01)
- Does not auto-delete domains from the nginx edge cert (revoke does this only
  when explicitly requested with `--apply`)
- Does not bypass certbot rate limits (operator responsibility)
- Does not manage certificates for non-edge-published services

## Implementation

### Files Created / Modified

| File | Change |
|------|--------|
| `.githooks/pre-push` | Honors `SKIP_CERT_VALIDATION=1` with bypass logging |
| `scripts/cert_lifecycle_manager.py` | New — programmatic cert lifecycle tool |
| `config/cert-sync-cron.yaml` | New — cron job definition for cert sync |
| `docs/adr/0414-cert-lifecycle-agent-tools-and-cron-sync.md` | This ADR |
| `docs/runbooks/cert-lifecycle-management.md` | New — operator runbook |
| `workstreams/active/ws-0414-cert-lifecycle-agent-tools.yaml` | Workstream entry |

### Bypass audit format

Every `SKIP_CERT_VALIDATION=1` push is logged to the gate-bypass log with:

```json
{
  "bypass": "skip_cert_validation",
  "source": "pre-push-hook",
  "reason_code": "<GATE_BYPASS_REASON_CODE>",
  "detail": "<GATE_BYPASS_DETAIL>",
  "timestamp": "2026-04-14T..."
}
```

Operators are expected to follow up with `make converge-nginx-edge env=production`
within one working day of a bypass.

## Consequences

**Positive**

- `SKIP_CERT_VALIDATION=1` now actually works — no more `--no-verify` for cert
  issues. Every bypass is audited.
- Subdomain+cert operations are one command — usable from shell, agent, and cron.
- cert_mismatch entries auto-repair daily before they accumulate and block pushes.
- Forked deployments without Hetzner DNS API have a documented, safe skip mode.
- LibreChat agent gains full cert lifecycle capability without SSH access.

**Negative / Trade-offs**

- `sync-missing --apply` changes live certs — the cron must run as a user with
  sudo access to certbot on the nginx edge host.
- cert_lifecycle_manager.py wraps Ansible playbooks for now (not a direct
  certbot CLI wrapper) — adds latency to agent tool calls (~30-60s per operation).
- New `platform_cert_validation_mode: skip` can mask real cert problems if
  operators leave it set to skip in production.

**Risk Mitigation**

- All mutating operations default to dry-run; `--apply` is required explicitly.
- `sync-missing` only adds domains to certs, never removes them (safe expansion).
- `platform_cert_validation_mode: skip` is only read from `.local/` (not committed
  to the repo), so it cannot accidentally propagate to the public mirror.

## Scenarios

### Scenario A: Developer pushes with 16 cert_mismatch entries (incident replay)

Before this ADR:
```bash
# Hook reports 16 cert_mismatch — operator has no working bypass
git push origin my-branch   # FAILS
SKIP_CERT_VALIDATION=1 git push origin my-branch  # SILENTLY IGNORED, still fails
git push --no-verify origin my-branch  # Works but skips ALL gates
```

After this ADR:
```bash
SKIP_CERT_VALIDATION=1 \
  GATE_BYPASS_REASON_CODE=cert-mismatch-pending-converge \
  GATE_BYPASS_DETAIL="16 cert_mismatch entries; converge-nginx-edge scheduled" \
  git push origin my-branch  # Passes, bypass logged
```

### Scenario B: Add a new service subdomain from LibreChat chat

Agent conversation: "Add a new subdomain `metrics.example.com` pointing to `10.10.10.92:3001`"

```bash
# Agent calls (via Dify tool):
python3 scripts/cert_lifecycle_manager.py create-subdomain \
  --domain metrics.example.com \
  --target 10.10.10.92 \
  --target-port 3001

# Output (dry-run):
# Would add metrics.example.com to subdomain-catalog.json
# Would add metrics.example.com to certificate-catalog.json
# Would run: make converge-nginx-edge env=production
# Use --apply to execute

# Agent asks user to confirm, then calls with --apply
```

### Scenario C: Cron auto-repair at 03:00

```
[cert-sync] 2026-04-14 03:00 UTC: scanning 53 domains...
[cert-sync] cert_mismatch: ci.example.com, bi.example.com
[cert-sync] running certbot renewal to add 2 missing SANs...
[cert-sync] reloading nginx...
[cert-sync] post-check: all 53 domains valid
[cert-sync] report: /var/log/cert-sync-20260414.json
```

### Scenario D: Fork without Hetzner DNS API

Operator sets in `.local/identity.yml`:
```yaml
platform_cert_validation_mode: warn
```

Pre-push gate prints warnings but does not block. Cert lifecycle manager still
works for all read operations (`list`, `status`); write operations print a note
that DNS-01 challenge is unavailable but HTTP-01 may work for some issuers.

## Related ADRs

- ADR 0375: Certificate validation and concordance enforcement (pre-push gate)
- ADR 0415: Postmortem — cert_mismatch gate forced `--no-verify` (incident)
- ADR 0101: Automated certificate lifecycle management (renewal timer pattern)
- ADR 0021: Public subdomain publication at NGINX edge (certbot + Hetzner DNS-01)
- ADR 0042: step-ca for SSH and internal TLS (internal certs — out of scope here)
- ADR 0407: Deployment-specific values and `.local/` overlay (identity.yml pattern)
