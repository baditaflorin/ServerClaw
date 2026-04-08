# ADR 0029: Dedicated Backup VM With Local PBS

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.30.0
- Implemented In Platform Version: 0.19.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

ADR 0020 selected an external CIFS target as the first practical backup destination, but live application is blocked because the target credentials and external endpoint do not currently exist in controller-local secrets.

At the same time, the platform now has:

- a stable internal guest network on `10.10.10.0/24`
- enough local host storage headroom to carve out a dedicated backup landing zone
- a clear operator requirement to stop waiting on external credentials and create a dedicated backup or replica VM now

That creates a pragmatic choice:

- either keep waiting for off-host credentials and remain without automated host-managed backups
- or create a dedicated backup VM on the same Proxmox node and use it as the first backup landing zone

The second option does not solve host-loss or site-loss recovery, because the VM still lives on the same hypervisor and the same underlying storage pool. It does, however, create a useful first recovery layer for guest corruption, accidental deletion, operator rollback, and restore drills.

## Decision

We will create a dedicated internal backup VM and run Proxmox Backup Server inside it.

Initial shape:

1. Create VM `160` named `backup-lv3` on `10.10.10.60`.
2. Run Proxmox Backup Server from Debian packages inside that VM.
3. Give the backup VM:
   - a small system disk for the guest OS
   - a dedicated larger secondary disk for the PBS datastore
4. Configure the Proxmox host to back up managed guests to the new PBS target.
5. Exclude the backup VM itself from the host backup job.
6. Keep the existing retention model from ADR 0020 unless a later datastore-specific policy replaces it.

## Replaceability Scorecard

- Capability Definition: `backup_repository` as defined by ADR 0020 backup policy, ADR 0100 recovery targets, and the backup-restore verification runbook.
- Contract Fit: strong for Proxmox guest backups, datastore verification, pruning, and operator-driven restore drills on the current platform.
- Data Export / Import: PBS datastores, prune policies, verification history, `storage.cfg` target declarations, and restore receipts are portable enough to seed a replacement backup system.
- Migration Complexity: medium because backup jobs, datastore copy time, restore verification, and retention enforcement all need parallel validation before cutover.
- Proprietary Surface Area: medium because PBS-native datastore format, prune semantics, and Proxmox host integration are optimized for the Proxmox stack.
- Approved Exceptions: the first implementation accepts PBS-native metadata and same-host datastore coupling as a time-bounded exception while off-host backup maturity continues.
- Fallback / Downgrade: guest-level file backups plus exported VM disk images to an external object store can preserve minimum recovery coverage if PBS must be retired before a full peer replacement is ready.
- Observability / Audit Continuity: backup job logs, datastore verify results, restore-verification receipts, and schedule history remain the continuity surface during migration.

## Vendor Exit Plan

- Reevaluation Triggers: failed restore drills, unacceptable datastore growth, unsupported retention needs, or a hard requirement for off-host-native replication that PBS cannot meet cleanly.
- Portable Artifacts: datastore inventories, prune and verify schedules, Proxmox storage target definitions, restore runbooks, restore receipts, and guest backup coverage manifests.
- Migration Path: stand up the replacement repository in parallel, copy or reseed the protected backup set, replay restore verification against the new target, then repoint Proxmox backup jobs and retire PBS after one successful full backup cycle.
- Alternative Product: Restic or BorgBackup backed by external object storage.
- Owner: platform recovery.
- Review Cadence: quarterly.

## Consequences

- The platform gets working, automated Proxmox backups without waiting on an external CIFS dependency.
- Restore operations become materially better because PBS provides a native Proxmox backup target and a clear datastore model.
- This is still the same failure domain as the hypervisor and its local storage, so it is not an off-host or disaster-recovery-grade solution.
- ADR 0020 remains relevant for retention policy, restore expectations, and scope boundaries, but its initial external-target implementation is superseded for the immediate rollout path.
- The live platform now has this backup path in place, but `platform_version` is intentionally unchanged until the merged automation is re-applied from `main`.
- A follow-up ADR is still required for true off-host replication, a second PBS node, object storage export, or any other cross-failure-domain design.

## Sources

- <https://pbs.proxmox.com/docs/proxmox-backup.pdf>
- <https://pbs.proxmox.com/docs/proxmox-backup-manager/man1.html>
- <https://pbs.proxmox.com/docs/configuration-files.html>
- <https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf>
