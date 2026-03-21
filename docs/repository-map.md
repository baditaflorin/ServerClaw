# Repository Map

This file explains where important information lives and which files are authoritative for each concern.

## Start Here

Read these in order when picking up the repository cold:

1. [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md)
2. [AGENTS.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/AGENTS.md)
3. [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
4. [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md)
5. [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
6. [docs/assistant-operator-guide.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/assistant-operator-guide.md)

## Source Of Truth By Topic

### High-level state

- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md): current summary, major milestones, and next steps
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml): desired state plus observed live state
- [VERSION](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION): current repository version only
- [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md): release-by-release history
- [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml): active branch-level implementation streams

### Protected integration files

These files are integration-owned and should normally be edited only during merge/release work on `main`:

- [VERSION](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION)
- [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md)
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md)

### Decision history

- [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr): architectural decisions and their implementation status

### Operational procedures

- [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks): operator procedures for access, install, networking, provisioning, and hardening
- [docs/release-process.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-process.md): branch, merge, and live-apply sequencing
- [docs/workstreams/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/README.md): how parallel implementation is organized
- [scripts/create-workstream.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/create-workstream.sh): creates the branch/worktree pair for a workstream
- [docs/runbooks/configure-public-ingress.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md): public edge forwarding from the host to the NGINX VM
- [docs/runbooks/configure-tailscale-access.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-tailscale-access.md): steady-state Tailscale subnet routing and operator onboarding
- [docs/runbooks/complete-security-baseline.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/complete-security-baseline.md): management firewall, TFA, TLS, and notifications
- [docs/runbooks/proxmox-api-automation.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/proxmox-api-automation.md): durable Proxmox API user and token lifecycle
- [docs/runbooks/monitoring-stack.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md): VM 140 monitoring stack convergence, operator flow, and verification

### Automation entry points

- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile): preferred command surface for common tasks
- [playbooks/site.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml): main Ansible entry point for the Proxmox host
- [playbooks/guest-access.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/guest-access.yml): guest SSH and access baseline enforcement
- [playbooks/monitoring-stack.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/monitoring-stack.yml): monitoring VM convergence plus Proxmox metric-server wiring

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
- [roles/proxmox_tailscale/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_tailscale/tasks/main.yml): Tailscale subnet-router installation and helper wiring
- [roles/proxmox_guests/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_guests/tasks/main.yml): template and VM provisioning
- [roles/linux_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/linux_access/tasks/main.yml): shared Linux SSH and `sudo` baseline
- [roles/proxmox_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_access/tasks/main.yml): Proxmox host and `pveum` access model
- [roles/proxmox_api_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_api_access/tasks/main.yml): durable Proxmox API automation identity and token verification
- [roles/proxmox_security/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_security/tasks/main.yml): Proxmox firewall, ACME, notifications, and TFA
- [roles/monitoring_vm/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_vm/tasks/main.yml): Grafana and InfluxDB convergence on the monitoring VM
- [roles/proxmox_metrics/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_metrics/tasks/main.yml): Proxmox external metric-server configuration for InfluxDB

## Change Rules

When a change affects live behavior, do not update only one layer.

Minimum expected updates for a meaningful infrastructure change:

- automation code
- relevant runbook
- relevant ADR if the change is architectural
- relevant workstream file and `workstreams.yaml` if the change is in flight on a branch
- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md) if the integrated current-state summary changed
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml) if `main` truth or observed state changed
- [VERSION](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION) and [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md) only when cutting a `main` release
- commit and push if the change was applied to the live platform

## Known Gaps

These areas are planned but not yet fully implemented:

- live apply of the Tailscale private access path
- live apply and dashboard build-out for the monitoring stack on `10.10.10.40`
- live apply of storage and backup automation
