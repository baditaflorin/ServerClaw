# ADR 0100: Formal RTO/RPO Targets and Disaster Recovery Playbook

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.97.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-23

## Context

ADR 0051 introduced control-plane backup, restore drills, and break-glass references, but it still left the platform without a measurable answer to the most important outage question:

> how long does full-platform recovery take after a total host loss?

The draft answer that existed before this ADR had two serious problems:

1. it described recovery order from memory instead of from the platform's actual VM layout
2. it assumed PBS could natively sync to a Hetzner Storage Box, which is not how PBS remotes work in practice

The current platform reality is:

- `backup-lv3` is the local PBS anchor VM on `10.10.10.60`
- its datastore lives on a dedicated 640 GB secondary disk attached to VM `160`
- the nightly host-side PBS backup job currently protects VMs `110`, `120`, `130`, `140`, and `150`
- no PBS remotes or PBS sync jobs are currently configured on `backup-lv3`
- no off-site copy of `backup-lv3` is currently recorded in live state

Without explicit targets, machine-readable readiness, and a documented tier order that matches the real topology, recovery remains partly improvised.

## Decision

We will define formal platform RTO/RPO targets, store them in machine-readable repo data, publish the ordered disaster recovery playbook, and expose a repo-managed readiness report.

The off-site recovery anchor is the **backup-lv3 PBS VM itself**:

- Proxmox keeps taking nightly guest backups into local PBS on `backup-lv3`
- a second, optional off-site Proxmox backup stores VM `160` on Hetzner Storage Box-backed external storage
- after a total host loss, the operator restores VM `160` first
- once PBS is back, the remaining VMs are restored from PBS in dependency order

This replaces the earlier incorrect idea of "PBS remote sync to Storage Box".

### Targets

| Scenario | RTO | RPO | Notes |
|---|---|---|---|
| Single service failure | < 5 min | 0 | Docker restart or targeted converge |
| VM failure with Postgres HA | < 1 min | 0 committed transactions | ADR 0098 target state |
| Stateless VM failure | < 30 min | 0 | nginx-lv3 or monitoring-lv3 reprovision/restore |
| Stateful VM failure without HA | < 2 h | < 24 h | docker-runtime-lv3 or backup-lv3 restore path |
| Full host recovery with off-site backup-lv3 copy | < 4 h | < 24 h | restore VM 160 first, then restore remaining VMs from PBS |
| Full host recovery with no backup | < 8 h | unbounded | repo-only rebuild; stateful data lost |

**Platform-wide RTO: < 4 hours.**

**Platform-wide RPO: < 24 hours.**

### Recovery tiers

#### Tier 0: Host reprovision
1. Reinstall Debian 13 on replacement Hetzner hardware
2. Reinstall Proxmox VE from Debian packages
3. Verify `pvesh get /version` works

#### Tier 1: Restore `backup-lv3`
1. Mount or reconnect the off-site storage target
2. Restore VM `160` (`backup-lv3`) from the latest off-site Proxmox backup
3. Verify PBS datastore visibility on `backup-lv3`

#### Tier 2: Restore stateful data services
1. Restore VM `150` (`postgres-lv3`) from PBS
2. Restore VM `120` (`docker-runtime-lv3`) from PBS
3. Verify `step-ca` and OpenBao health

#### Tier 3: Restore edge and observability
1. Restore VM `140` (`monitoring-lv3`) from PBS
2. Restore VM `110` (`nginx-lv3`) from PBS
3. Verify Grafana and Keycloak through the edge

#### Tier 4: Restore build infrastructure
1. Restore VM `130` (`docker-build-lv3`) from PBS
2. Verify the build gateway path

#### Tier 5: Platform verification sweep
1. Run `make dr-status`
2. Run `lv3 release status`
3. Run a service-health sweep from the operator CLI

### Repo implementation

This ADR is implemented in repository automation by:

- [config/disaster-recovery-targets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/disaster-recovery-targets.json) for machine-readable targets and tier deadlines
- [scripts/disaster_recovery_runbook.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/disaster_recovery_runbook.py) for the structured recovery plan
- [config/windmill/scripts/disaster-recovery-runbook.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/disaster-recovery-runbook.py) for the Windmill wrapper
- [scripts/generate_dr_report.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_dr_report.py) plus `make dr-status` for current DR readiness
- [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py) `release status` output for the DR review criterion in ADR 0110
- [playbooks/backup-vm.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/backup-vm.yml) plus [roles/proxmox_backups](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/proxmox_backups) for the optional off-site backup of VM `160`
- [docs/runbooks/disaster-recovery.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/disaster-recovery.md) and [docs/runbooks/break-glass.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/break-glass.md) for the operator path

### Off-site backup model

The off-site copy uses Proxmox-managed external storage and protects the whole `backup-lv3` VM.

Why this model:

- it matches the actual architecture, where PBS runs inside VM `160`
- restoring VM `160` restores the PBS catalog and datastore together
- Hetzner Storage Box can be consumed through Proxmox-managed CIFS storage
- PBS native remote sync requires another PBS endpoint, so it is not the right Storage Box path

The repo therefore treats the off-site copy as:

- storage id: `lv3-backup-offsite`
- schedule: `04:00`
- protected VM: `160`
- retention: keep last `3`, daily `7`, weekly `5`, monthly `12`

### Recovery drill policy

- table-top review: once per quarter
- live off-site recovery drill: once per year

Table-top completion is recorded under [receipts/dr-table-top-reviews](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/dr-table-top-reviews).

## Consequences

**Positive**

- The platform now has explicit recovery targets instead of an implied backup story.
- The recovery order now matches the current VM topology.
- The repo exposes a first-class readiness report instead of making operators infer DR posture from multiple ADRs.
- The off-site strategy is technically correct for the current architecture.

**Negative / Trade-offs**

- The off-site path is still pending live credential provisioning for the Storage Box-backed target.
- The < 4 h RTO still assumes operator access to Hetzner reinstall and break-glass materials.
- Recovery remains operator-initiated; the repo provides execution guidance and readiness, not autonomous failover.

## Alternatives Considered

- **Keep DR informal**: rejected because the platform already has enough moving parts for recovery order mistakes to matter.
- **Use PBS native sync to Storage Box**: rejected because PBS native remotes target PBS endpoints, not Storage Box CIFS or SFTP.
- **Replicate to a second Hetzner server**: rejected for now as disproportionate for the current budget and operating model.

## Related ADRs

- ADR 0020: Initial storage and backup model
- ADR 0029: Dedicated backup VM with local PBS
- ADR 0051: Control-plane backup, recovery, and break-glass
- ADR 0098: Postgres HA
- ADR 0099: Automated backup restore verification
- ADR 0110: Platform versioning and release readiness
