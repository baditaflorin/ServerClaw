# ADR 0408: Generic Inventory Hostnames

- **Status**: Implementing
- **Date**: 2026-04-11
- **Extends**: ADR 0407 (Generic-by-Default Codebase with Local Overlay)

## Context

ADR 0407 established the generic-by-default architecture where committed code uses
generic values and deployment-specific values are injected at runtime. Despite
significant progress (publish pipeline down from 6,482 to 412 sanitized files),
the single biggest remaining driver of divergence between private and public repos
is the `-lv3` suffix on Ansible inventory hostnames.

**Analysis** of the 412 files still requiring sanitization:
- **264 files (64%)** only need sanitization because VM names end in `-lv3`
- 22 files have domain references only (example.com)
- 19 files have both VM names + domains
- 13 files have IPs/PII only

The `-lv3` suffix is a deployment identifier with no functional purpose — Ansible
connects via `ansible_host` IP, not DNS hostname resolution. Removing it from
inventory names eliminates sanitization for 264 files.

## Decision

Rename all Ansible inventory hostnames from `<role>-lv3` to `<role>` (production)
and from `<role>-staging-lv3` to `<role>-staging` (staging). This is an
inventory-only rename — actual Proxmox VM hostnames are not affected.

### Hostname Mapping (24 VMs)

| Old (production) | New (production) | Old (staging) | New (staging) |
|-------------------|------------------|---------------|---------------|
| nginx-lv3 | nginx | nginx-staging-lv3 | nginx-staging |
| docker-runtime-lv3 | docker-runtime | docker-runtime-staging-lv3 | docker-runtime-staging |
| docker-build-lv3 | docker-build | docker-build-staging-lv3 | docker-build-staging |
| monitoring-lv3 | monitoring | monitoring-staging-lv3 | monitoring-staging |
| postgres-lv3 | postgres | postgres-staging-lv3 | postgres-staging |
| postgres-replica-lv3 | postgres-replica | | |
| backup-lv3 | backup | backup-staging-lv3 | backup-staging |
| coolify-lv3 | coolify | | |
| coolify-apps-lv3 | coolify-apps | | |
| artifact-cache-lv3 | artifact-cache | artifact-cache-staging-lv3 | artifact-cache-staging |
| runtime-ai-lv3 | runtime-ai | | |
| runtime-control-lv3 | runtime-control | | |
| runtime-general-lv3 | runtime-general | | |
| runtime-comms-lv3 | runtime-comms | | |
| runtime-apps-lv3 | runtime-apps | | |
| postgres-apps-lv3 | postgres-apps | | |
| postgres-data-lv3 | postgres-data | | |
| postgres-vm-lv3 | postgres-vm | | |

### What Changes

1. **inventory/hosts.yml** — All hostname definitions
2. **playbook_execution_host_patterns** — All hostname mappings
3. **Playbook hosts: directives** — All conditional hostname selections
4. **Task files** — delegate_to, when conditions, variable references
5. **Role defaults** — VM name references in default values
6. **Config files** — Monitoring targets, service catalogs, dependency graphs
7. **Scripts** — Hardcoded VM name references
8. **host_vars/runtime-control-lv3.yml** → renamed to host_vars/runtime-control.yml
9. **publication-sanitization.yaml** — VM name patterns removed (no longer needed)

### What Does NOT Change

- Actual Proxmox VM hostnames (they keep `-lv3` on the hypervisor)
- The `proxmox-host` inventory hostname (stays as-is, handled by TOPOLOGY_HOST)
- IP addresses (unchanged)
- Domain references (`example.com` — handled separately by identity.yml)
- `.local/` overlay files

## Consequences

- **Publish pipeline**: 412 → ~148 sanitized files (64% reduction)
- **Private/public parity**: 264 more files become identical between repos
- **Fork friendliness**: New deployments no longer inherit "lv3" naming
- **Convergence**: Requires full reconvergence since Ansible inventory names change
  (Ansible facts cache should be cleared)
- **Risk**: Low — this is a mechanical rename. The actual VM hostnames, IPs,
  and connection parameters are unchanged.
