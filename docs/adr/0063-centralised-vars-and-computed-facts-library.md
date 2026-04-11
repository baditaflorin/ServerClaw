# ADR 0063: Centralised Vars And Computed Facts Library

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.68.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

Variables that describe the platform — VM names, IP assignments, internal DNS names, port numbers, storage paths, and identity metadata — are currently scattered across:

- `inventory/group_vars/all.yml`
- `inventory/host_vars/proxmox-host.yml`
- `versions/stack.yaml`
- individual role `defaults/main.yml` files
- inline `vars:` blocks inside playbooks

This means the same fact (e.g. the postgres VM's IP address) is often referenced from different sources in different roles. A change to the postgres VM IP requires hunting down every reference manually. Agents querying the platform for topology facts have no single source of truth short of reading all of these files.

## Decision

We will establish a centralised vars and computed facts library with a clear resolution order.

Structure:

1. `inventory/group_vars/all.yml` remains the primary home for platform-wide facts that change rarely (domain names, hypervisor version pins, package lists)
2. a new `inventory/group_vars/platform.yml` holds computed references derived from `stack.yaml` — VM IPs, internal hostnames, port assignments, and service URLs — generated or validated by a script at `make validate` time
3. individual roles declare only their own role-specific defaults in `defaults/main.yml`; they reference platform facts by variable name without redeclaring them
4. a custom filter plugin at `filter_plugins/platform_facts.py` provides helpers for common derivations (e.g. constructing an internal URL from a VM name and port) so roles do not encode the derivation logic inline
5. agents and operators can run `make show-platform-facts` to dump the full resolved variable set for a given host without executing a playbook

Resolution precedence (highest to lowest):

- host_vars > group_vars/all > group_vars/platform > role defaults

## Consequences

- A single change to a VM's IP in `stack.yaml` propagates to all roles automatically via the generated `platform.yml`.
- Agents can answer topology questions by reading `platform.yml` and `stack.yaml` instead of scanning all role defaults.
- The generation step at `make validate` adds a dependency: the inventory must be consistent with `stack.yaml` before validation passes.
- The filter plugin must be maintained and documented alongside the variable library.

## Boundaries

- Secrets are never stored in the vars library; they come from OpenBao or `controller-local-secrets.json` at runtime.
- The `platform.yml` file is generated output and must not be hand-edited; its source is always `stack.yaml` plus `host_vars`.
- Per-environment overrides are out of scope; this is a single-environment platform.

## Implementation Notes

- [scripts/generate_platform_vars.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/generate_platform_vars.py) now generates and validates the committed [inventory/group_vars/platform.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/group_vars/platform.yml) facts library from canonical stack and host inputs.
- [filter_plugins/platform_facts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/filter_plugins/platform_facts.py) now provides service and guest lookup helpers so roles can consume the generated catalog without repeating `hostvars[...]` derivations inline.
- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/Makefile) now exposes `make generate-platform-vars`, `make validate-generated-vars`, and `make show-platform-facts HOST=<host>`.
- [scripts/validate_repo.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_repo.sh) and [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/validate_repository_data_models.py) now fail when the committed generated facts file drifts from [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/versions/stack.yaml) or [inventory/host_vars/proxmox-host.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/host_vars/proxmox-host.yml).
- Current consumers now read generated platform facts in [roles/netbox_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/netbox_runtime), [roles/windmill_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/windmill_runtime), [roles/open_webui_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/open_webui_runtime), [roles/openbao_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/openbao_runtime), [roles/mattermost_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/mattermost_runtime), [roles/proxmox_ntopng](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/proxmox_ntopng), [roles/rag_context_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/rag_context_runtime), [roles/portainer_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/portainer_runtime), and the shared observability or publication defaults that formerly duplicated computed URLs.
