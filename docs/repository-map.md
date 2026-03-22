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
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml): desired state plus observed live state, including the enforced identity taxonomy and managed-principal inventory
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
- [docs/runbooks/workflow-catalog-and-execution-contracts.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/workflow-catalog-and-execution-contracts.md): canonical workflow ids, preferred entry points, and execution metadata
- [docs/runbooks/command-catalog-and-approval-gates.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/command-catalog-and-approval-gates.md): mutating command contracts, approval policies, and rollback guidance
- [docs/runbooks/controller-local-secrets-and-preflight.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/controller-local-secrets-and-preflight.md): controller-local secret manifest usage and the standard preflight check
- [docs/runbooks/controller-automation-toolkit.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/controller-automation-toolkit.md): shared controller-side Python helper boundary for repo-local scripts
- [docs/runbooks/control-plane-communication-lanes.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/control-plane-communication-lanes.md): canonical command, API, message, and event lane policy with the governed-surface catalog
- [docs/runbooks/live-apply-receipts-and-verification-evidence.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/live-apply-receipts-and-verification-evidence.md): structured evidence model for real platform applies
- [docs/runbooks/generate-status-documents.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/generate-status-documents.md): generated README status fragments and validation flow
- [docs/runbooks/identity-taxonomy-and-managed-principals.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/identity-taxonomy-and-managed-principals.md): ADR 0046 identity classes, required metadata, and the current principal inventory
- [docs/runbooks/configure-netbox.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-netbox.md): NetBox runtime, proxy, and repo-sync operator flow
- [docs/release-process.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-process.md): branch, merge, and live-apply sequencing
- [docs/workstreams/README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/README.md): how parallel implementation is organized
- [scripts/create-workstream.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/create-workstream.sh): creates the branch/worktree pair for a workstream
- [docs/runbooks/configure-public-ingress.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md): public edge forwarding from the host to the NGINX VM
- [docs/runbooks/configure-tailscale-access.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-tailscale-access.md): steady-state Tailscale subnet routing and operator onboarding
- [docs/runbooks/complete-security-baseline.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/complete-security-baseline.md): management firewall, TFA, TLS, and notifications
- [docs/runbooks/proxmox-api-automation.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/proxmox-api-automation.md): durable Proxmox API user and token lifecycle
- [docs/runbooks/monitoring-stack.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md): VM 140 monitoring stack convergence, operator flow, and verification
- [docs/runbooks/deploy-uptime-kuma.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/deploy-uptime-kuma.md): Uptime Kuma convergence, publication, and repo-local monitor management
- [docs/runbooks/repair-guest-netplan-mac-drift.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/repair-guest-netplan-mac-drift.md): break-glass recovery when guest netplan MAC matches drift from Proxmox NIC state

### Automation entry points

- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile): preferred command surface for common tasks
- [scripts/command_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/command_catalog.py): validates and renders mutating command contracts and evaluates approval gates
- [scripts/workflow_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/workflow_catalog.py): validates and renders the canonical workflow execution catalog
- [scripts/controller_automation_toolkit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/controller_automation_toolkit.py): shared controller-side path, manifest, subprocess, and CLI helper primitives for repo-local Python scripts
- [scripts/preflight_controller_local.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/preflight_controller_local.py): checks controller-local secret and environment prerequisites for a named workflow
- [scripts/live_apply_receipts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/live_apply_receipts.py): validates and renders structured live-apply receipts
- [scripts/control_plane_lanes.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/control_plane_lanes.py): validates and renders the canonical control-plane communication-lane catalog
- [scripts/generate_status_docs.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py): renders generated README status fragments from canonical state and verifies they are current
- [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repository_data_models.py): validates canonical repository data models and cross-checks stack state against host vars
- [scripts/validate_repo.sh](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repo.sh): repository validation entry point behind `make validate`
- [filter_plugins/service_topology.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/filter_plugins/service_topology.py): derives edge publication and DNS artifacts from the canonical service topology catalog
- [playbooks/site.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml): main Ansible entry point for the Proxmox host
- [playbooks/guest-access.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/guest-access.yml): guest SSH and access baseline enforcement
- [playbooks/monitoring-stack.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/monitoring-stack.yml): monitoring VM convergence plus Proxmox metric-server wiring
- [playbooks/netbox.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/netbox.yml): NetBox PostgreSQL, runtime, host proxy, and repo-sync convergence
- [playbooks/uptime-kuma.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/uptime-kuma.yml): Uptime Kuma DNS, runtime, and edge-publication convergence
- [scripts/uptime_kuma_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/uptime_kuma_tool.py): repo-local client for Uptime Kuma bootstrap and monitor management
- [scripts/netbox_inventory_sync.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/netbox_inventory_sync.py): repo-local NetBox API synchronizer for the canonical topology, IPAM, and governed service inventory
- [.github/workflows/validate.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.github/workflows/validate.yml): CI path that runs the same `make validate` contract as local operators

### Shared automation inputs

- [inventory/hosts.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml): host and guest inventory layout
- [inventory/group_vars/all.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/all.yml): cross-role platform facts and intentionally shared policy values
- [inventory/group_vars/lv3_guests.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/lv3_guests.yml): guest-side connection behavior
- [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml): per-host topology, guest definitions, and the canonical `lv3_service_topology` catalog
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json): canonical machine-readable workflow catalog for preferred entry points, preflight requirements, validation targets, and runbook ownership
- [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json): canonical mutating command-contract catalog for approval policy, operator inputs, evidence expectations, and failure guidance
- [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json): canonical machine-readable catalog of command, API, message, and event lane boundaries and their governed surfaces
- [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json): machine-readable controller-local secret manifest for repo workflows and `.local/` prerequisites
- [config/uptime-kuma/monitors.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/uptime-kuma/monitors.json): canonical repo-managed Uptime Kuma monitor definitions
- [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies): structured receipt set for historically applied and verified live changes

### Reusable automation units

- reusable role interfaces now live beside each role in `roles/<role>/defaults/main.yml` and `roles/<role>/README.md`
- reusable roles should validate required inputs near the top of `tasks/main.yml`

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
- [roles/guest_observability/tasks/setup.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/guest_observability/tasks/setup.yml): shared guest-side Telegraf, token, and Influx repository plumbing for service telemetry
- [roles/docker_runtime_observability/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/docker_runtime_observability/tasks/main.yml): Docker runtime VM container telemetry collection and Telegraf shipping into InfluxDB
- [roles/docker_build_observability/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/docker_build_observability/tasks/main.yml): Docker build VM metrics collection and Telegraf shipping into InfluxDB
- [roles/uptime_kuma_runtime/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/uptime_kuma_runtime/tasks/main.yml): Uptime Kuma Compose deployment on `docker-runtime-lv3`
- [roles/hetzner_dns_records/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/hetzner_dns_records/tasks/main.yml): idempotent Hetzner DNS publication for repo-managed records including `uptime.lv3.org`
- [roles/monitoring_vm/templates/_grafana_dashboard_macros.j2](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_vm/templates/_grafana_dashboard_macros.j2): shared Grafana panel macros for the managed monitoring dashboards
- [roles/monitoring_vm/templates/lv3-platform-overview.json.j2](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_vm/templates/lv3-platform-overview.json.j2): managed high-level Grafana dashboard definition for the Proxmox host and guest fleet
- [roles/monitoring_vm/templates/lv3-vm-detail.json.j2](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_vm/templates/lv3-vm-detail.json.j2): managed per-VM Grafana dashboard definition
- [roles/nginx_observability/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/nginx_observability/tasks/main.yml): loopback-only `stub_status` plus Telegraf shipping for `nginx-lv3`
- [docs/adr/0022-nginx-guest-observability-via-telegraf-and-stub-status.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0022-nginx-guest-observability-via-telegraf-and-stub-status.md): architecture decision for NGINX service-level monitoring
- [docs/adr/0040-docker-runtime-container-telemetry-via-telegraf-docker-input.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0040-docker-runtime-container-telemetry-via-telegraf-docker-input.md): architecture decision for Docker runtime container telemetry on the runtime VM
- [docs/adr/0028-docker-build-vm-build-count-telemetry-via-cli-wrapper-events.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0028-docker-build-vm-build-count-telemetry-via-cli-wrapper-events.md): architecture decision for Docker build count and duration telemetry on the build VM
- [roles/proxmox_metrics/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_metrics/tasks/main.yml): Proxmox external metric-server configuration for InfluxDB
- [roles/netbox_postgres/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/netbox_postgres/tasks/main.yml): PostgreSQL role, database, and mirrored password handling for NetBox
- [roles/netbox_runtime/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/netbox_runtime/tasks/main.yml): private NetBox Compose deployment and bootstrap-token verification on `docker-runtime-lv3`
- [roles/netbox_sync/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/netbox_sync/tasks/main.yml): repo-managed synchronization of canonical topology, IPAM, and governed service inventory into NetBox

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
- live apply of storage and backup automation
