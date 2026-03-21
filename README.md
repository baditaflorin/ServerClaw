# proxmox_florin_server

Infrastructure-as-code workspace for building a dedicated Hetzner host into a Proxmox VE node.

The preferred bootstrap path is now Hetzner Rescue System plus `installimage`, not the automatic installer and not the VNC installer.

## Current status

Debian 13 is installed on the host, Proxmox VE is installed from the Debian package path, and routine SSH/Ansible access now uses the non-root `ops` identity instead of `root`.

Verified on 2026-03-21:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@65.108.75.123
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

Initial guest provisioning is now implemented and applied:

```text
110 nginx-lv3            10.10.10.10
120 docker-runtime-lv3   10.10.10.20
130 docker-build-lv3     10.10.10.30
140 monitoring-lv3       10.10.10.40
9000 debian13-cloud-template
```

The private SSH jump path through the Proxmox host to the guests is working.

The current access posture is:

```text
ops SSH + sudo for routine host work
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
Let's Encrypt certificate active for proxmox.lv3.org
sendmail notification endpoint and catch-all matcher configured
ops@pam protected by TOTP
```

## Documents

- [Changelog](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md)
- [Repository map](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/repository-map.md)
- [Assistant operator guide](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/assistant-operator-guide.md)
- [Release process](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-process.md)
- [Workstreams registry](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
- [Workstreams guide](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/README.md)
- [Initial access runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/initial-access.md)
- [Configure public ingress runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md)
- [Complete security baseline runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/complete-security-baseline.md)
- [Proxmox API automation runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/proxmox-api-automation.md)
- [Monitoring stack runbook](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md)
- [ADR 0001: Bootstrap model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0001-bootstrap-dedicated-host-with-ansible.md)
- [ADR 0002: Target Proxmox VE 9 on Debian 13](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0002-target-proxmox-ve-9-on-debian-13.md)
- [ADR 0003: Prefer Rescue plus installimage](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0003-prefer-hetzner-rescue-plus-installimage-for-bootstrap.md)
- [ADR 0004: Install Proxmox VE from Debian packages](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0004-install-proxmox-ve-from-debian-packages.md)
- [ADR 0005: Single-node first topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0005-single-node-first-topology.md)
- [ADR 0006: Security baseline](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0006-security-baseline-for-proxmox-host.md)
- [ADR 0007: Agent-oriented access model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0007-agent-oriented-access-model.md)
- [ADR 0008: Versioning model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0008-versioning-model-for-repo-and-host.md)
- [ADR 0009: DRY and solid engineering principles](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0009-dry-and-solid-engineering-principles.md)
- [ADR 0010: Initial Proxmox VM topology](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0010-initial-proxmox-vm-topology.md)
- [ADR 0011: Monitoring VM with Grafana and Proxmox metrics](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0011-monitoring-vm-with-grafana-and-proxmox-metrics.md)
- [ADR 0012: Proxmox host bridge and NAT network](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0012-proxmox-host-bridge-and-nat-network.md)
- [ADR 0013: Public ingress and guest egress model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0013-public-ingress-and-guest-egress-model.md)
- [ADR 0014: Operator access to private guest network](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0014-operator-access-to-private-guest-network.md)
- [ADR 0015: lv3.org DNS and subdomain model](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0015-lv3-org-dns-and-subdomain-model.md)
- [ADR 0016: Provision guests from Debian 13 cloud template](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0016-provision-guests-from-debian-13-cloud-template.md)
- [ADR 0017: ADR lifecycle and implementation metadata](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0017-adr-lifecycle-and-implementation-metadata.md)
- [ADR 0018: Non-root operations for host and guests](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0018-non-root-operations-for-host-and-guests.md)
- [ADR 0019: Parallel ADR delivery with workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0019-parallel-adr-delivery-with-workstreams.md)

## Versioning

This repo now tracks three distinct things:

- Repository version: [`VERSION`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION)
- Desired platform and observed host state: [`versions/stack.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- Versioning rules: [ADR 0008](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0008-versioning-model-for-repo-and-host.md)

Current values on `main`:

- `repo_version`: `0.15.0`
- `platform_version`: `0.11.0`
- `observed_os`: `Debian 13`
- `observed_proxmox_installed`: `true`
- `observed_pve_manager_version`: `9.1.6`

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
- `VERSION` is bumped on merge to `main`, not on every branch-local change
- `platform_version` is bumped only after merged work is applied live from `main`

## Engineering stance

This repository is intentionally opinionated:

- DRY by default
- explicit versioning for repo and platform state
- small reversible infrastructure changes
- clear separation between bootstrap, security, storage, networking, and Proxmox object management

## Active Parallel Work

- [ADR 0011 monitoring workstream](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0011-monitoring.md)
- [ADR 0014 Tailscale workstream](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams/adr-0014-tailscale.md)

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
- [playbooks/proxmox-install.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/proxmox-install.yml)
- [roles/proxmox_repository/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_repository/tasks/main.yml)
- [roles/proxmox_kernel/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_kernel/tasks/main.yml)
- [roles/proxmox_platform/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_platform/tasks/main.yml)
- [roles/proxmox_network/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_network/tasks/main.yml)
- [docs/runbooks/configure-public-ingress.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-public-ingress.md)
- [roles/proxmox_guests/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_guests/tasks/main.yml)
- [roles/linux_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/linux_access/tasks/main.yml)
- [roles/proxmox_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_access/tasks/main.yml)
- [roles/proxmox_api_access/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_api_access/tasks/main.yml)
- [roles/proxmox_security/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_security/tasks/main.yml)
- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile)
- [docs/runbooks/install-proxmox.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/install-proxmox.md)
- [docs/runbooks/configure-proxmox-network.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-proxmox-network.md)
- [docs/runbooks/provision-guests.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/provision-guests.md)
- [docs/runbooks/harden-access.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/harden-access.md)
- [playbooks/guest-access.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/guest-access.yml)
- [playbooks/monitoring-stack.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/monitoring-stack.yml)
- [docs/runbooks/complete-security-baseline.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/complete-security-baseline.md)
- [scripts/totp_provision.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/totp_provision.py)
- [docs/runbooks/monitoring-stack.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/monitoring-stack.md)
- [roles/monitoring_vm/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_vm/tasks/main.yml)
- [roles/proxmox_metrics/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_metrics/tasks/main.yml)
