# ADR 0409 — Zero-Sanitization Publication

| Field | Value |
|---|---|
| **Status** | Implemented |
| **Date** | 2026-04-11 |
| **Concerns** | publication, security |
| **Supersedes** | — |
| **Implementation** | 2026-04-11 |

## Context

The publication pipeline (`publish_to_serverclaw.py`) sanitized committed code
before pushing to the public ServerClaw repository. At its peak, this required
modifying **6,482 files**. ADR 0407 (generic-by-default) and ADR 0408 (generic
inventory hostnames) reduced this to ~128 files, but a residual set of
deployment-specific literals remained:

- Operator domain in 73 config catalogs, scripts, and metadata files
- Topology host identifier in 66 files
- Public IPv4/IPv6 addresses in 8 files
- Operator PII (names, emails) in 7 files
- Repository checkout name in 14 files
- Generated inventory/monitoring configs (6 files)

These literals existed because the codebase was written deployment-first: real
values were committed, and the publication pipeline replaced them with generic
placeholders. This created an ongoing maintenance burden — every new file with a
domain reference required remembering to sanitize it.

## Decision

**Invert the publication model**: committed code uses generic placeholder values
everywhere. Deployment-specific values are injected at runtime via
`.local/identity.yml` (loaded as Ansible extra-vars with highest precedence).

This eliminates ALL Tier C regex replacements. The publication pipeline's
string_replacements section becomes a defensive safety net with zero expected
matches.

### Changes

1. **`identity.yml` made generic**: `platform_domain: example.com`,
   `platform_operator_email: operator@example.com`,
   `platform_operator_name: "Platform Operator"`,
   `platform_repo_name: platform_server`

2. **Topology host renamed** to `proxmox-host` in Ansible inventory, host_vars
   filename, and all references. `TOPOLOGY_HOST` in `platform/repo.py` updated.

3. **All source files generalized**: 129 files, 2,581 replacements applying the
   same transformations the publication pipeline used to apply at publish time.

4. **Public IPs replaced** with RFC 5737 documentation IPs (`203.0.113.x`),
   IPv6 with RFC 3849 (`2001:db8::`). Real IPs provided via
   `.local/identity.yml`.

5. **Generated files gitignored**: `platform.yml`, `platform_hairpin.yml`,
   Prometheus rules/targets, Uptime Kuma monitors — all derived from source
   catalogs and regenerated at deploy time.

6. **Operator PII removed** from committed code: names, emails, and SSH key
   comments replaced with generic values.

### Hostname Mapping

| Before (old) | After (generic) |
|--------|-------|
| deployment-specific topology host | `proxmox-host` |
| deployment-specific host_vars file | `host_vars/proxmox-host.yml` |
| deployment-specific template image | `debian-base-template` |

### Runtime Override Mechanism

`.local/identity.yml` provides deployment-specific values. Example structure:

```yaml
platform_domain: your-domain.tld
platform_operator_email: you@your-domain.tld
platform_operator_name: "Your Name"
platform_repo_name: your_repo_name
host_public_hostname: your-server-hostname
proxmox_node_name: your-proxmox-node
management_ipv4: YOUR.PUBLIC.IP.ADDR
management_gateway4: YOUR.GATEWAY.IP
management_ipv6: "your:ipv6::addr"
hetzner_ipv4_route_network: YOUR.ROUTE.NETWORK
```

Ansible loads this via `-e @.local/identity.yml` (extra-vars have highest
precedence, overriding group_vars and host_vars).

## Consequences

### Positive

- **Publication sanitization reaches zero**: Tier C regex replacements match
  zero files. The publication pipeline becomes a no-op for sanitization.
- **New files are safe by default**: developers write `example.com` naturally;
  no need to remember to add sanitization patterns.
- **Fork operators benefit**: the committed code is immediately functional for
  any domain — just edit `.local/identity.yml`.
- **Leak risk eliminated**: no deployment-specific values exist in committed
  code to accidentally leak.

### Negative

- **Runtime dependency on `.local/identity.yml`**: every `ansible-playbook`
  invocation must include `-e @.local/identity.yml`. The Makefile handles this
  automatically, but direct ansible-playbook calls need the flag.
- **Generated files must be regenerated**: the 6 gitignored files need
  `make regenerate-all` before convergence. This is a one-time step after
  cloning.
- **Historical references remain**: ADR filenames, release notes, and
  slugified identifiers retain the original domain slug. These don't match
  any leak markers.

### Tier A Replacements (retained)

Four files are still replaced during publication, but for **fork UX** rather
than sanitization. The committed versions are already generic; the templates
add setup instructions and placeholder comments for new operators:

1. `identity.yml` — adds `<-- CHANGE` annotations
2. `hosts.yml` — provides a fork-ready inventory template
3. `host_vars/proxmox-host.yml` — provides fork-ready host configuration
4. `operators.yaml` — provides example operator entry

## Publication Pipeline Status

| Metric | Before ADR 0407 | After ADR 0407 | After ADR 0408 | After ADR 0409 |
|--------|-----------------|----------------|----------------|----------------|
| Tier C sanitized files | 6,482 | 412 | 128 | **0** |
| Tier A replaced files | 4 | 4 | 4 | 4 (UX only) |
| Leak marker matches | — | 0 | 0 | 0 |
