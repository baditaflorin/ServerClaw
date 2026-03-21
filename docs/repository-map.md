# Repository Map

This file explains where important information lives and which files are authoritative for each concern.

## Start Here

Read these in order when picking up the repository cold:

1. [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md)
2. [AGENTS.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/AGENTS.md)
3. [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
4. [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md)
5. [docs/assistant-operator-guide.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/assistant-operator-guide.md)

## Source Of Truth By Topic

### High-level state

- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md): current summary, major milestones, and next steps
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml): desired state plus observed live state
- [VERSION](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION): current repository version only
- [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md): release-by-release history

### Decision history

- [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr): architectural decisions and their implementation status

### Operational procedures

- [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks): operator procedures for access, install, networking, provisioning, and hardening
- [docs/runbooks/configure-public-ingress.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md): public edge forwarding from the host to the NGINX VM

### Automation entry points

- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile): preferred command surface for common tasks
- [playbooks/site.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml): main Ansible entry point for the Proxmox host
- [playbooks/guest-access.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/guest-access.yml): guest SSH and access baseline enforcement

### Shared automation inputs

- [inventory/hosts.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml): host and guest inventory layout
- [inventory/group_vars/all.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/all.yml): shared variables across the platform
- [inventory/group_vars/lv3_guests.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/lv3_guests.yml): guest-side connection behavior
- [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml): per-host topology and guest definitions

### Reusable automation units

- [roles/proxmox_repository/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_repository/tasks/main.yml): Proxmox package repository setup
- [roles/proxmox_kernel/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_kernel/tasks/main.yml): kernel and boot prerequisites
- [roles/proxmox_platform/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_platform/tasks/main.yml): core Proxmox packages and platform setup
- [roles/proxmox_network/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_network/tasks/main.yml): bridge and NAT configuration
- [roles/proxmox_guests/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_guests/tasks/main.yml): template and VM provisioning
- [roles/linux_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/linux_access/tasks/main.yml): shared Linux SSH and `sudo` baseline
- [roles/proxmox_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_access/tasks/main.yml): Proxmox host and `pveum` access model

## Change Rules

When a change affects live behavior, do not update only one layer.

Minimum expected updates for a meaningful infrastructure change:

- automation code
- relevant runbook
- relevant ADR if the change is architectural
- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md) if the current-state summary changed
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml) if desired or observed state changed
- [VERSION](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION) and [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md) if the repository contract changed

## Known Gaps

These areas are planned but not yet fully implemented:

- public ingress forwarding to the NGINX VM
- Proxmox firewall policy
- TFA for human Proxmox accounts
- ACME or other managed TLS for browser access
- notifications and alert routing
- Tailscale private access path
