# ADR 0165: Playbook and Role Metadata Standard for Agent Discovery

- Status: Proposed
- Implementation Status: Proposed
- Date: 2026-03-26

## Context

This repository uses Ansible extensively for infrastructure automation. LLM agents onboarding need to understand:

- What each playbook does and what it modifies
- What inputs (variables) a playbook or role requires
- What outputs or side effects to expect
- Which roles a playbook uses and why
- What dependencies each role has

Without machine-discoverable metadata, agents must:

- Read entire playbook/role files to understand purpose
- Trial-and-error to discover required variables
- Search through multiple files to understand dependencies
- Waste tokens understanding implementation details when only the contract matters

A standard metadata header in every playbook and role would enable agents to quickly understand:
- The contract (inputs, outputs, side effects)
- The purpose and when to use it
- Critical dependencies and prerequisites
- Failure modes and recovery procedures

## Decision

All Ansible playbooks and roles in this repository must include a **metadata block** at the start documenting:

1. **Purpose**: One-sentence description of what this automation does
2. **Use case**: When and why to run this (e.g., "Run on new Proxmox host after bootstrap")
3. **Inputs**: Required and optional variables with types and descriptions
4. **Outputs**: What this automation creates, modifies, or generates
5. **Idempotency**: Whether this can be safely run multiple times
6. **Dependencies**: Other roles, playbooks, or ADRs this depends on
7. **Related**: Links to relevant ADRs, runbooks, or documentation
8. **Author/Date**: Who documented this and when

### Playbook Format

Every playbook must include metadata comment block at the top:

```yaml
---
# =============================================================================
# Playbook: site.yml
# Purpose: Bootstrap Proxmox host from Debian to production-ready state
# Use case: Run once after initial Debian 13 installation via Hetzner installer
#
# Inputs:
#   - proxmox_node_name (string, required): hostname for Proxmox node
#   - timezone (string, optional, default=UTC): system timezone
#
# Outputs:
#   - Proxmox VE installed and running on port 8006
#   - Host firewall enabled with rules from inventory
#   - SSH key-only access configured
#   - Monitoring agents deployed if configured
#
# Idempotency: Fully idempotent - safe to run multiple times
#
# Dependencies:
#   - ADR 0001: Bootstrap model
#   - ADR 0002: Debian 13 + Proxmox VE 9
#   - ADR 0006: Security baseline
#   - Requires: Debian 13 already installed on target host
#
# Related ADRs: 0001, 0002, 0004, 0006, 0007
# Related Runbooks: docs/runbooks/bootstrap-proxmox-host.md
#
# Author: LV3 Platform
# Last Updated: 2026-03-21
# =============================================================================

- name: Bootstrap Proxmox host
  hosts: proxmox_host
  become: yes
  # ... rest of playbook ...
```

### Role Format

Every role must include metadata in `roles/role_name/meta/main.yml`:

```yaml
---
# =============================================================================
# Role: security_baseline
# Purpose: Apply security hardening baseline to a Linux host
# Use case: Applied to every Debian/Ubuntu host during bootstrap
#
# Inputs:
#   - ssh_allow_root_login (bool, optional, default=false)
#   - ssh_disable_password_auth (bool, optional, default=true)
#   - firewall_enabled (bool, optional, default=true)
#   - audit_logging (bool, optional, default=true)
#
# Outputs:
#   - SSH configured with key-only access (unless ssh_allow_root_login=true)
#   - Fail2ban configured if enabled
#   - Auditd configured if audit_logging=true
#   - Firewall rules applied
#
# Idempotency: Fully idempotent
#
# Dependencies:
#   - Ansible 2.10+
#   - Related role: host_packages (should run first)
#   - Related ADR 0006: Security baseline
#
# Variables Used From:
#   - group_vars/all.yml: security_* variables
#   - host_vars/{{ inventory_hostname }}.yml: host-specific overrides
#
# Handler Actions:
#   - Restarts sshd when SSH config changes
#   - Reloads firewall rules
#
# Example Invocation:
#   - role: security_baseline
#     vars:
#       ssh_disable_password_auth: true
#       firewall_enabled: true
#
# Author: LV3 Platform
# Last Updated: 2026-03-21
# =============================================================================

namespace: lv3.platform
name: security_baseline
version: 1.0.0
description: Apply security hardening baseline to Linux hosts
license:
  - MIT
authors:
  - LV3 Platform
dependencies:
  - role: host_packages
```

### README.md in Roles

Each role should include `roles/role_name/README.md`:

```markdown
# Role: security_baseline

## Purpose
Apply security hardening baseline to a Linux host.

## When to Use
- Every Debian/Ubuntu host during bootstrap
- When refreshing security baselines
- When security policies change

## Variables
| Variable | Type | Default | Description |
|---|---|---|---|
| ssh_allow_root_login | bool | false | Allow SSH root login |
| ssh_disable_password_auth | bool | true | Require SSH keys only |
| firewall_enabled | bool | true | Enable host firewall |
| audit_logging | bool | true | Enable auditd |

## Example
```yaml
- hosts: webservers
  roles:
    - role: security_baseline
      vars:
        firewall_enabled: true
        ssh_disable_password_auth: true
```

## Dependencies
- Requires: host_packages role (runs first)
- ADR 0006: Security baseline

## Handlers
- `restart sshd`: Restarts SSH daemon when config changes
- `reload firewall`: Reloads firewall rules

## Author
LV3 Platform

## Updated
2026-03-21
```

### Minimum Discoverable Metadata

If a playbook or role cannot include full documentation, it MUST at minimum include:

```yaml
# Purpose: [One sentence describing what this does]
# Use case: [When to run this]
# Dependencies: [ADRs, roles, prerequisites]
# Idempotency: [Yes/No - is it safe to run multiple times?]
```

## Consequences

**Positive**

- Agents can understand playbook/role purpose without reading implementation
- Dependencies are clear and machine-discoverable
- When to use each automation is explicit
- Reduces token overhead for agent onboarding
- Enables automated discovery and documentation generation
- Makes it easier to understand which playbooks to run in which order

**Negative / Trade-offs**

- Requires discipline to maintain metadata as playbooks evolve
- Initial documentation of existing playbooks/roles requires effort
- Metadata must be kept in sync with actual behavior

## Boundaries

- This standard applies to all new playbooks and roles
- Existing playbooks and roles should be updated as they are modified
- Metadata should be in YAML comments or Ansible meta/ directory, not separate files
- Do not duplicate metadata - if documented in meta/main.yml, don't repeat in playbook itself

## Implementation Path

1. Create metadata template file at `playbooks/.metadata-template.yml`
2. Update new playbooks/roles to include metadata headers
3. Gradually add metadata to existing high-value playbooks/roles
4. Create a metadata extraction tool (for future documentation generation)

## Related ADRs

- ADR 0001: Bootstrap model
- ADR 0031: Repository validation pipeline
- ADR 0163: Repository structure index
- ADR 0164: ADR metadata index

## Agent Quick Reference

When you encounter a playbook or role:

1. Check the metadata header first (top 20 lines)
2. Look at "Purpose" and "Use case" to understand when to use it
3. Check "Inputs" for required variables
4. Check "Dependencies" for what must run first
5. Check "Idempotency" to understand if it's safe to run multiple times
6. If metadata is missing, add it as part of your work
