# ADR 0406: Automated DNS Propagation From Single IP Source of Truth

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: n/a
- Implemented In Platform Version: n/a
- Implemented On: 2026-04-11
- Date: 2026-04-11
- Concern: Platform Reliability, DNS, IoC
- Depends on: ADR 0076 (Subdomain Governance), ADR 0139 (Subdomain Exposure Audit), ADR 0252 (Route DNS Assertion Ledger), ADR 0385 (Identity IoC)
- Tags: dns, ioc, automation, platform-vars, subdomain-catalog, hetzner

---

## Context

### The incident (2026-04-11)

Commit `31d24a6cd` ("Prepare repository for public GitHub release") replaced `management_ipv4` in
`inventory/host_vars/proxmox-host.yml` with the RFC 5737 documentation address `203.0.113.1`.
When `make configure-edge-publication` was subsequently run, the broken IP propagated into:

1. `inventory/group_vars/platform.yml` — all 138 `target:` DNS record values
2. `config/subdomain-catalog.json` — 50 subdomain entries
3. Hetzner DNS — 45 live A records

All 45 production subdomains (`wiki.example.com`, `sso.example.com`, `agents.example.com`, etc.) started
resolving to `203.0.113.1` (unreachable). The platform was completely offline.

### Why it wasn't caught automatically

The `configure-edge-publication` target ran `subdomain_exposure_audit.py --validate` **against
the already-stale `subdomain-catalog.json`**, which itself contained the wrong IP. The audit
validated consistency between catalog and registry — both wrong — and passed.

Additionally, `generate_platform_vars.py` was **not invoked** as part of `configure-edge-publication`,
so `platform.yml` was never refreshed from the canonical source before deployment.

A second compounding bug: `generate_platform_vars.py` **failed entirely** when run manually because
commit `06fb2499d` parameterised hostnames with `{{ platform_domain }}` (from `identity.yml`), but
the generator only loaded `host_vars/proxmox-host.yml`. It had no knowledge of `identity.yml` and
threw `references unknown host var 'platform_domain'`, making the generator broken for months.

---

## Decision

### 1. Fix the generator: load identity.yml as a source

`generate_platform_vars.py` now loads `inventory/group_vars/all/identity.yml` in `load_sources()`
and merges its plain scalar values into `host_vars` before template resolution. This allows
`{{ platform_domain }}` and similar identity tokens to resolve in strings like
`public_hostname: nginx.{{ platform_domain }}`.

Only non-Jinja2 string/int/bool values are merged (values containing `{{` are skipped) so that
partially-rendered template strings never propagate into the generated output.

### 2. Wire the generator into configure-edge-publication

`make configure-edge-publication` now runs:

```
generate-platform-vars          # regenerate platform.yml from proxmox-host.yml + identity.yml
subdomain_exposure_audit --write-registry --validate  # refresh catalog + registry, then validate
generate-changelog-portal docs  # (unchanged)
public-edge.yml Ansible play    # (unchanged)
validate-certificates           # (unchanged)
```

`--write-registry` ensures the subdomain catalog and exposure registry are **always regenerated**
from the freshly-generated `platform.yml` before validation. An operator changing `management_ipv4`
in `proxmox-host.yml` and running `make configure-edge-publication` will have the correct IP flow
through to Hetzner DNS without any manual intervention.

### 3. The full automated chain

```
proxmox-host.yml      (single source: real IP)
      │
      ▼  generate_platform_vars.py --write
platform.yml            (derived: resolved DNS targets, guest IPs, topology)
      │
      ▼  subdomain_exposure_audit.py --write-registry
subdomain-catalog.json  (derived: per-subdomain DNS records with IPs)
subdomain-exposure-registry.json
      │
      ▼  public-edge.yml Ansible play (hetzner_dns_records role)
Hetzner DNS             (live: A records updated idempotently)
      │
      ▼  validate-certificates
Certificate validator   (confirms TLS works end-to-end)
```

Each step is idempotent. Adding a new service adds it to `platform_services.yml` with
`target_host: nginx-edge` — the IP resolves automatically through the chain on the next
`make configure-edge-publication` run. No manual DNS management required.

---

## Consequences

### Positive

- Changing `management_ipv4` in one place propagates to all DNS records automatically.
- `generate_platform_vars.py` now works correctly with `{{ platform_domain }}` tokens.
- No more manual `sed` or Hetzner API calls to fix DNS records.
- The audit validates the *freshly-generated* catalog, not a stale committed artifact.
- New services added to `platform_services.yml` get DNS records without any manual step.

### Negative / Trade-offs

- `configure-edge-publication` is slightly slower (adds ~2s for generator + audit).
- `platform.yml` and `subdomain-catalog.json` will always be regenerated on convergence,
  meaning they should be treated as derived artifacts (committed for cache/audit, but never
  hand-edited).

### Invariants

- `proxmox-host.yml:management_ipv4` is the **only place** the public IP lives.
- `identity.yml:platform_domain` is the **only place** the domain name lives.
- `platform.yml`, `subdomain-catalog.json`, and `subdomain-exposure-registry.json` are
  **derived** — regenerated on every `configure-edge-publication` run.
