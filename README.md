# proxmox_florin_server

Infrastructure-as-code workspace for building a dedicated Hetzner host into a Proxmox VE node.

The preferred bootstrap path is now Hetzner Rescue System plus `installimage`, not the automatic installer and not the VNC installer.

## Current status

Debian 13 is installed on the host, Proxmox VE is installed from the Debian package path, and routine SSH/Ansible access now works over the host Tailscale IP instead of `root` on the public IPv4.

Verified on 2026-03-22:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95
```

Observed remote kernel:

```text
Linux Debian-trixie-latest-amd64-base 6.17.13-2-pve
```

Bootstrap key in use:

```text
SHA256:+wOwI8QKECFX9y2hlFMfBLP1m67PC0y9PYlO8+s0isQ
```

Installed Proxmox versions observed on 2026-03-21:

```text
proxmox-ve: 9.1.0
pve-manager: 9.1.6
running kernel: 6.17.13-2-pve
```

Management services are active and `pveproxy` is listening on `:8006`.

Proxmox host networking is now converged to:

```text
vmbr0  public bridge on enp7s0
vmbr10 internal bridge on 10.10.10.1/24
```

Host-side IPv4 forwarding and NAT are enabled for `10.10.10.0/24` guest egress.

Public ingress is now converged to the single-edge model:

```text
65.108.75.123:80  -> 10.10.10.10:80
65.108.75.123:443 -> 10.10.10.10:443
```

The private SSH jump path through the Proxmox host to the guests is working.

<!-- BEGIN GENERATED: platform-status -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

### Current Values
| Field | Value |
| --- | --- |
| Repository version | `0.42.0` |
| Platform version | `0.20.0` |
| Observed check date | `2026-03-22` |
| Observed OS | `Debian 13` |
| Observed Proxmox version | `9.1.6` |
| Observed kernel | `6.17.13-2-pve` |

### Managed Guests
| VMID | Name | IPv4 | Running |
| --- | --- | --- | --- |
| 110 | `nginx-lv3` | `10.10.10.10` | `true` |
| 120 | `docker-runtime-lv3` | `10.10.10.20` | `true` |
| 130 | `docker-build-lv3` | `10.10.10.30` | `true` |
| 140 | `monitoring-lv3` | `10.10.10.40` | `true` |
| 150 | `postgres-lv3` | `10.10.10.50` | `true` |
| 160 | `backup-lv3` | `10.10.10.60` | `true` |

Template VM: `9000` `debian13-cloud-template`

### Published Service Inventory
| Hostname | Service | Exposure | Owner |
| --- | --- | --- | --- |
| `build.lv3.org` | `docker-build` | `informational-only` | `docker-build-lv3` |
| `database.lv3.org` | `postgres` | `private-only` | `postgres-lv3` |
| `docker.lv3.org` | `docker-runtime` | `informational-only` | `docker-runtime-lv3` |
| `grafana.lv3.org` | `grafana` | `edge-published` | `monitoring-lv3` |
| `nginx.lv3.org` | `nginx-edge` | `edge-static` | `nginx-lv3` |
| `proxmox.lv3.org` | `proxmox-ui` | `informational-only` | `proxmox_florin` |
| `uptime.lv3.org` | `uptime-kuma` | `edge-published` | `docker-runtime-lv3` |

### Latest Live-Apply Evidence
| Capability | Receipt |
| --- | --- |
| `backup_vm` | `2026-03-22-adr-0029-backup-vm-live-apply` |
| `build_telemetry` | `2026-03-22-adr-0028-build-telemetry-live-apply` |
| `docker_runtime` | `2026-03-22-adr-0023-docker-runtime-live-apply` |
| `monitoring` | `2026-03-22-adr-0011-monitoring-live-apply` |
| `postgres_vm` | `2026-03-22-adr-0026-postgres-vm-live-apply` |
| `public_edge_publication` | `2026-03-22-adr-0021-edge-publication-live-apply` |
| `runtime_container_telemetry` | `2026-03-22-adr-0040-runtime-container-telemetry-live-apply` |
| `uptime_kuma` | `2026-03-22-adr-0027-uptime-kuma-live-apply` |
<!-- END GENERATED: platform-status -->

The current access posture is:

```text
ops SSH + sudo for routine host work
routine host SSH over the Proxmox Tailscale IP
ops@pam for routine Proxmox administration
lv3-automation@pve API token for durable Proxmox object management
ops SSH + sudo for guest VMs
root key-only break-glass on the Proxmox host
root disabled for guest SSH
password SSH disabled on host and guests
```

The current host security posture is:

```text
Proxmox firewall enabled for host management traffic
SSH and port 8006 limited to declared management source ranges
Tailscale is the primary management path for the host
Let's Encrypt certificate active for proxmox.lv3.org
sendmail notification endpoint and catch-all matcher configured
ops@pam protected by TOTP
```

The current monitoring posture is:

```text
InfluxDB 2 running on 10.10.10.40:8086
Grafana running on 10.10.10.40:3000
Proxmox metric server influxdb-http active and writing to the proxmox bucket
Grafana published at https://grafana.lv3.org via the NGINX edge
Grafana folder LV3 provisioned from repo
Grafana dashboard LV3 Platform Overview provisioned from repo
Per-VM dashboards provisioned for nginx-lv3, docker-runtime-lv3, docker-build-lv3, and monitoring-lv3
Overview and VM dashboards together cover the Proxmox host plus nginx-lv3, docker-runtime-lv3, docker-build-lv3, and monitoring-lv3 individually
NGINX guest telemetry now includes loopback-only stub_status plus Telegraf shipping into InfluxDB
Dashboard now also includes nginx service panels for active connections, requests per second, accepts and handled rates, and connection states
Docker runtime monitoring now includes container-level CPU, memory, network, health, and snapshot panels for docker-runtime-lv3
```

The current Docker runtime posture is:

```text
Docker Engine 29.3.0 installed from Docker's official Debian repository
Docker Compose plugin v5.1.1 available through `docker compose`
Docker live-restore enabled
json-file logging capped at 10m with 5 retained files
ops present in the local docker group on docker-runtime-lv3
telegraf active on docker-runtime-lv3 with Docker socket access for container telemetry
Uptime Kuma running from /opt/uptime-kuma and published at https://uptime.lv3.org
repo-local Uptime Kuma auth and monitor management material stored under .local/uptime-kuma
```

The current PostgreSQL posture is:

```text
PostgreSQL running on postgres-lv3 at 10.10.10.50
database.lv3.org resolves to the Proxmox host Tailscale IP 100.118.189.95
database access is proxied only on Tailscale port 5432
65.108.75.123:5432 remains closed on the public IPv4
guest firewall only accepts proxied PostgreSQL traffic from 10.10.10.1/32
```

The current backup posture is:

```text
backup-lv3 runs Proxmox Backup Server on 10.10.10.60
PBS datastore proxmox is mounted at /mnt/datastore/proxmox on the dedicated backup disk
Proxmox storage lv3-backup-pbs points to 10.10.10.60:8007
nightly job backup-lv3-nightly protects VMIDs 110, 120, 130, 140, and 150 at 02:30
restore-oriented verification is documented and includes artifact listing plus test backup validation
this is still same-host recovery, not off-host disaster recovery
```

## Documents

<!-- BEGIN GENERATED: document-index -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

### Core Documents
- [Changelog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md)
- [Repository map](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/repository-map.md)
- [Assistant operator guide](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/assistant-operator-guide.md)
- [Release process](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-process.md)
- [Workstreams registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
- [Workstreams guide](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/README.md)

### Runbooks
- [Complete Security Baseline Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/complete-security-baseline.md)
- [Configure Backup VM](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-backup-vm.md)
- [Configure Docker Runtime Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-docker-runtime.md)
- [Configure Edge Publication](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-edge-publication.md)
- [Configure PostgreSQL VM Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-postgres-vm.md)
- [Configure Proxmox Network Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-proxmox-network.md)
- [Configure Public Ingress Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md)
- [Configure Storage And Backups](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-storage-and-backups.md)
- [Configure Tailscale Private Access](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-tailscale-access.md)
- [Controller Automation Toolkit](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/controller-automation-toolkit.md)
- [Controller-Local Secrets And Preflight Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/controller-local-secrets-and-preflight.md)
- [Deploy Uptime Kuma](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/deploy-uptime-kuma.md)
- [Generate Status Documents](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/generate-status-documents.md)
- [Harden Access Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/harden-access.md)
- [Initial Access Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/initial-access.md)
- [Install Proxmox Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/install-proxmox.md)
- [Live Apply Receipts And Verification Evidence](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/live-apply-receipts-and-verification-evidence.md)
- [Monitoring Stack Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md)
- [Prepare Mail Platform Rollout](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/prepare-mail-platform-rollout.md)
- [Provision Guests Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/provision-guests.md)
- [Proxmox API Automation Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/proxmox-api-automation.md)
- [Repair Guest Netplan MAC Drift](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/repair-guest-netplan-mac-drift.md)
- [Validate Repository Automation Runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/validate-repository-automation.md)
- [Workflow Catalog And Execution Contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/workflow-catalog-and-execution-contracts.md)

### ADRs
- [ADR 0001: Bootstrap Dedicated Host With Ansible](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0001-bootstrap-dedicated-host-with-ansible.md)
- [ADR 0002: Target Proxmox VE 9 on Debian 13](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0002-target-proxmox-ve-9-on-debian-13.md)
- [ADR 0003: Prefer Hetzner Rescue Plus Installimage For Bootstrap](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0003-prefer-hetzner-rescue-plus-installimage-for-bootstrap.md)
- [ADR 0004: Install Proxmox VE From Debian Packages](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0004-install-proxmox-ve-from-debian-packages.md)
- [ADR 0005: Single-Node First Topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0005-single-node-first-topology.md)
- [ADR 0006: Security Baseline For Proxmox Host](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0006-security-baseline-for-proxmox-host.md)
- [ADR 0007: Agent-Oriented Access Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0007-agent-oriented-access-model.md)
- [ADR 0008: Versioning Model For Repo And Host](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0008-versioning-model-for-repo-and-host.md)
- [ADR 0009: DRY And Solid Engineering Principles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0009-dry-and-solid-engineering-principles.md)
- [ADR 0010: Initial Proxmox VM Topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0010-initial-proxmox-vm-topology.md)
- [ADR 0011: Monitoring VM With Grafana And Proxmox Metrics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0011-monitoring-vm-with-grafana-and-proxmox-metrics.md)
- [ADR 0012: Proxmox Host Bridge And NAT Network](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0012-proxmox-host-bridge-and-nat-network.md)
- [ADR 0013: Public Ingress And Guest Egress Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0013-public-ingress-and-guest-egress-model.md)
- [ADR 0014: Operator Access To Private Guest Network](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0014-operator-access-to-private-guest-network.md)
- [ADR 0015: lv3.org DNS And Subdomain Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0015-lv3-org-dns-and-subdomain-model.md)
- [ADR 0016: Provision Guests From Debian 13 Cloud Template](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0016-provision-guests-from-debian-13-cloud-template.md)
- [ADR 0017: ADR Lifecycle And Implementation Metadata](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0017-adr-lifecycle-and-implementation-metadata.md)
- [ADR 0018: Non-Root Operations For Host And Guests](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0018-non-root-operations-for-host-and-guests.md)
- [ADR 0019: Parallel ADR Delivery With Workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0019-parallel-adr-delivery-with-workstreams.md)
- [ADR 0020: Initial Storage And Backup Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0020-initial-storage-and-backup-model.md)
- [ADR 0021: Public Subdomain Publication At The NGINX Edge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0021-public-subdomain-publication-at-the-nginx-edge.md)
- [ADR 0022: NGINX Guest Observability Via Telegraf And Stub Status](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0022-nginx-guest-observability-via-telegraf-and-stub-status.md)
- [ADR 0023: Docker Runtime VM Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0023-docker-runtime-vm-baseline.md)
- [ADR 0024: Docker Guest Security Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0024-docker-guest-security-baseline.md)
- [ADR 0025: Compose-Managed Runtime Stacks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0025-compose-managed-runtime-stacks.md)
- [ADR 0026: Dedicated PostgreSQL VM Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0026-dedicated-postgresql-vm-baseline.md)
- [ADR 0027: Uptime Kuma On The Docker Runtime VM](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0027-uptime-kuma-on-the-docker-runtime-vm.md)
- [ADR 0028: Docker Build VM Build Count And Duration Telemetry Via CLI Wrapper Events](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0028-docker-build-vm-build-count-telemetry-via-cli-wrapper-events.md)
- [ADR 0029: Dedicated Backup VM With Local PBS](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0029-dedicated-backup-vm-with-local-pbs.md)
- [ADR 0030: Role Interface Contracts And Defaults Boundaries](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0030-role-interface-contracts-and-defaults-boundaries.md)
- [ADR 0031: Repository Validation Pipeline For Automation Changes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0031-repository-validation-pipeline-for-automation-changes.md)
- [ADR 0032: Shared Guest Observability Framework](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0032-shared-guest-observability-framework.md)
- [ADR 0033: Declarative Service Topology Catalog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0033-declarative-service-topology-catalog.md)
- [ADR 0034: Controller-Local Secret Manifest And Preflight](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0034-controller-local-secret-manifest-and-preflight.md)
- [ADR 0035: Workflow Catalog And Machine-Readable Execution Contracts](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0035-workflow-catalog-and-machine-readable-execution-contracts.md)
- [ADR 0036: Live Apply Receipts And Verification Evidence](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0036-live-apply-receipts-and-verification-evidence.md)
- [ADR 0037: Schema-Validated Repository Data Models](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0037-schema-validated-repository-data-models.md)
- [ADR 0038: Generated Status Documents From Canonical State](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0038-generated-status-documents-from-canonical-state.md)
- [ADR 0039: Shared Controller Automation Toolkit](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0039-shared-controller-automation-toolkit.md)
- [ADR 0040: Docker Runtime Container Telemetry Via Telegraf Docker Input](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0040-docker-runtime-container-telemetry-via-telegraf-docker-input.md)
- [ADR 0041: Dockerized Mail Platform For Server Delivery, API Automation, And Grafana Observability](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0041-dockerized-mail-platform-for-server-delivery-api-and-observability.md)

### Workstream Documents
- [Workstream ADR 0011: Monitoring Stack Rollout](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0011-monitoring.md)
- [Workstream ADR 0014: Tailscale Private Access Rollout](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0014-tailscale.md)
- [Workstream ADR 0020: Initial Storage And Backup Model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0020-backups.md)
- [Workstream ADR 0023: Docker Runtime VM Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0023-docker-runtime.md)
- [Workstream ADR 0024: Docker Guest Security Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0024-docker-security.md)
- [Workstream ADR 0025: Compose-Managed Runtime Stacks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0025-docker-compose-stacks.md)
- [Workstream ADR 0026: Dedicated PostgreSQL VM Baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0026-postgres-vm.md)
- [Workstream ADR 0027: Uptime Kuma On The Docker Runtime VM](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0027-uptime-kuma.md)
- [Workstream ADR 0028: Docker Build VM Build Count And Duration Telemetry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0028-build-telemetry.md)
- [Workstream ADR 0029: Dedicated Backup VM With Local PBS](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0029-backup-vm.md)
- [Workstream ADR 0040: Docker Runtime Container Telemetry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0040-runtime-container-telemetry.md)
- [Workstream ADR 0041: Dockerized Mail Platform With API, Grafana Telemetry, And Failover Delivery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0041-email-platform.md)
<!-- END GENERATED: document-index -->

## Versioning

This repo now tracks three distinct things:

- Repository version: [`VERSION`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION)
- Desired platform and observed host state: [`versions/stack.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- Versioning rules: [ADR 0008](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0008-versioning-model-for-repo-and-host.md)

Current values on `main`:

<!-- BEGIN GENERATED: version-summary -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

| Field | Value |
| --- | --- |
| Repository version | `0.42.0` |
| Platform version | `0.20.0` |
| Observed OS | `Debian 13` |
| Observed Proxmox installed | `true` |
| Observed PVE manager version | `9.1.6` |
<!-- END GENERATED: version-summary -->

ADR metadata now tracks both acceptance and implementation:

- decision status
- implementation status
- first repo version implemented
- first platform version implemented
- implementation date

Repository releases are summarized in [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md).

## Delivery Model

This repository now supports parallel implementation:

- ADRs remain the architecture truth
- active implementation is tracked in [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
- each active implementation stream gets its own file in [docs/workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams)
- each workstream should run on its own `codex/` branch and preferably its own git worktree
- shared release files are reconciled during integration on `main`, not rewritten independently on every workstream branch
- `VERSION` is bumped on merge to `main`, not on every branch-local change
- `platform_version` is bumped only after merged work is applied live from `main`

## Engineering stance

This repository is intentionally opinionated:

- DRY by default
- explicit versioning for repo and platform state
- small reversible infrastructure changes
- clear separation between bootstrap, security, storage, networking, and Proxmox object management

## Merged Workstreams

<!-- BEGIN GENERATED: merged-workstreams -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_status_docs.py). Do not edit this block by hand.

| ADR | Title | Status | Doc |
| --- | --- | --- | --- |
| `0011` | Monitoring stack rollout | `live_applied` | [adr-0011-monitoring.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0011-monitoring.md) |
| `0014` | Tailscale private access rollout | `merged` | [adr-0014-tailscale.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0014-tailscale.md) |
| `0020` | Initial storage and backup model | `merged` | [adr-0020-backups.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0020-backups.md) |
| `0023` | Docker runtime VM baseline | `live_applied` | [adr-0023-docker-runtime.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0023-docker-runtime.md) |
| `0026` | Dedicated PostgreSQL VM baseline | `merged` | [adr-0026-postgres-vm.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0026-postgres-vm.md) |
| `0027` | Uptime Kuma rollout on the Docker runtime VM | `merged` | [adr-0027-uptime-kuma.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0027-uptime-kuma.md) |
| `0028` | Docker build VM build count and duration telemetry | `live_applied` | [adr-0028-build-telemetry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0028-build-telemetry.md) |
| `0029` | Dedicated backup VM with local PBS | `merged` | [adr-0029-backup-vm.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0029-backup-vm.md) |
| `0040` | Docker runtime container telemetry | `live_applied` | [adr-0040-runtime-container-telemetry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0040-runtime-container-telemetry.md) |
| `0041` | Dockerized mail platform with API, Grafana telemetry, and failover delivery | `merged` | [adr-0041-email-platform.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0041-email-platform.md) |
<!-- END GENERATED: merged-workstreams -->

## Planned workflow

1. Inspect disks, networking, and current Debian 13 base state.
2. Establish the steady-state operator access path with Tailscale, replacing the temporary jump-host-only flow.
3. Implement the monitoring stack on `10.10.10.40`.
4. Configure storage and backups.
5. Extend notifications beyond the host baseline where needed.
6. Commit the resulting automation and operational docs in this repo.

## Automation

The first executable automation scaffold now exists:

- [ansible.cfg](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/ansible.cfg)
- [inventory/hosts.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml)
- [inventory/host_vars/proxmox_florin.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/host_vars/proxmox_florin.yml)
- [playbooks/site.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml)
- [playbooks/public-edge.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/public-edge.yml)
- [playbooks/proxmox-install.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/proxmox-install.yml)
- [playbooks/docker-runtime.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/docker-runtime.yml)
- [playbooks/backup-vm.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/backup-vm.yml)
- [playbooks/uptime-kuma.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/uptime-kuma.yml)
- [roles/proxmox_repository/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_repository/tasks/main.yml)
- [roles/proxmox_kernel/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_kernel/tasks/main.yml)
- [roles/proxmox_platform/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_platform/tasks/main.yml)
- [roles/proxmox_network/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_network/tasks/main.yml)
- [roles/proxmox_tailscale/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_tailscale/tasks/main.yml)
- [roles/nginx_edge_publication/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/nginx_edge_publication/tasks/main.yml)
- [docs/runbooks/configure-public-ingress.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md)
- [docs/runbooks/configure-edge-publication.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-edge-publication.md)
- [docs/runbooks/configure-tailscale-access.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-tailscale-access.md)
- [roles/proxmox_guests/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_guests/tasks/main.yml)
- [roles/linux_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/linux_access/tasks/main.yml)
- [roles/docker_runtime/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/docker_runtime/tasks/main.yml)
- [roles/backup_vm/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/backup_vm/tasks/main.yml)
- [roles/uptime_kuma_runtime/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/uptime_kuma_runtime/tasks/main.yml)
- [roles/proxmox_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_access/tasks/main.yml)
- [roles/proxmox_api_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_api_access/tasks/main.yml)
- [roles/proxmox_security/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_security/tasks/main.yml)
- [roles/proxmox_backups/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_backups/tasks/main.yml)
- [roles/hetzner_dns_records/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/hetzner_dns_records/tasks/main.yml)
- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile)
- [docs/runbooks/install-proxmox.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/install-proxmox.md)
- [docs/runbooks/configure-proxmox-network.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-proxmox-network.md)
- [docs/runbooks/provision-guests.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/provision-guests.md)
- [docs/runbooks/harden-access.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/harden-access.md)
- [playbooks/guest-access.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/guest-access.yml)
- [playbooks/monitoring-stack.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/monitoring-stack.yml)
- [docs/runbooks/configure-docker-runtime.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-docker-runtime.md)
- [docs/runbooks/complete-security-baseline.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/complete-security-baseline.md)
- [scripts/totp_provision.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/totp_provision.py)
- [scripts/uptime_kuma_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/uptime_kuma_tool.py)
- [docs/runbooks/monitoring-stack.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md)
- [roles/monitoring_vm/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_vm/tasks/main.yml)
- [roles/proxmox_metrics/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_metrics/tasks/main.yml)
