# ADR 0302: Restic For Encrypted File-Level Backup Of Platform Configuration And State Artifacts

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.115
- Implemented In Platform Version: 0.130.75
- Implemented On: 2026-03-31
- Date: 2026-03-29

## Context

The Proxmox Backup Server (PBS) on `backup` (ADR 0029) performs scheduled
VM-level snapshots and PostgreSQL dumps. This protects application data and OS
state at the VM granularity. It does not protect the platform's operational
artefacts at the file level:

- `config/` — 87+ service configuration catalogs, correction-loop definitions,
  timeout hierarchy, SLO catalog
- `receipts/` — live-apply receipts, backup-coverage ledger, drift reports, SBOM
  and CVE receipts (ADR 0298)
- `versions/stack.yaml` — canonical deployed version record
- `docs/adr/` — all 300+ architecture decision records

These files live in the Git repository, so their history is preserved in Gitea.
However:

- Gitea itself is a service on the platform; if `docker-runtime` suffers a
  catastrophic storage failure before PBS runs its next snapshot, recent receipt
  writes and live-apply attestations that were not yet committed to the repo are
  lost
- certain receipts (e.g. SBOM and CVE reports under `receipts/sbom/` and
  `receipts/cve/`) are large binary-adjacent JSON blobs that are not committed to
  Git to avoid repository bloat; they exist only on the filesystem
- the controller-local secrets manifest (`config/controller-local-secrets.json`,
  ADR 0034) and the OpenBao agent token files are never committed to the repo and
  are not covered by PBS VM snapshots in their current form

Restic (`restic/restic`) is a Go-based backup tool that encrypts every snapshot
with a repository key, deduplicates blocks across snapshots, and supports multiple
storage backends including S3-compatible object storage. It is BSD-2-licensed,
ships as a single Go binary (~30 MB), and has been in active production use since
2015. Its REST API mode and JSON output enable fully programmatic backup and
restore operations without human interaction.

MinIO is already deployed on the platform (ADR 0274) and exposes an
S3-compatible API. It is the natural Restic backend for platform-local file
backups.

## Decision

We will deploy **Restic** as a scheduled backup agent for platform configuration
and state artefacts, using MinIO as the S3 backend.

### Deployment rules

- Restic runs as a scheduled Windmill job (`restic-config-backup`) and as a
  systemd timer on the controller host where receipts are written
- the Restic repository encryption password is stored in OpenBao (ADR 0043) and
  injected at runtime; it is never stored on disk in plaintext
- the Restic binary version is pinned in `versions/stack.yaml` and updated via
  the Renovate Bot process (ADR 0297)
- the MinIO bucket used as the Restic repository is created with Object Lock
  in GOVERNANCE mode so that no backup snapshot can be deleted or overwritten
  without an explicit operator action

### What is backed up

| Source path | Schedule | Retention |
|---|---|---|
| `receipts/` (all JSON artefacts) | every 6 hours | keep 90 daily, 12 monthly |
| `config/` | on every successful live-apply | keep 30 daily, 6 monthly |
| `versions/stack.yaml` | on every successful live-apply | keep 30 daily |
| Controller-local secrets manifest | daily | keep 90 daily |
| Falco rule overrides (`config/falco/`) | on change | keep 30 daily |

The `docs/adr/` directory is not backed up by Restic because it is fully covered
by the Gitea repository history.

### Programmatic restore-readiness rule

- after every Restic snapshot, the Windmill job runs `restic check --read-data-subset=5%`
  to verify repository integrity and blob deduplication consistency
- the `restic snapshots --json` output is parsed and the latest snapshot timestamp
  for each source path is written to `receipts/restic-snapshots-latest.json`; the
  backup-coverage assertion ledger (ADR 0271) consumes this file to confirm each
  path is covered and within the freshness SLA
- if a snapshot is older than its scheduled interval plus a 30-minute grace
  period, a `platform.backup.stale` NATS event is emitted (ADR 0276) and a
  critical restic backup ntfy notification is sent (ADR 0299)

### Restore procedure rule

- restoring from Restic requires only the MinIO endpoint URL and the repository
  password from OpenBao; both are documented in the platform runbook
- the restore path is exercised monthly via a Windmill dry-run job that restores
  the latest `receipts/` snapshot to a temporary directory and verifies the
  restored file count against the snapshot metadata

## Consequences

**Positive**

- receipts that are not committed to Git (SBOM, CVE reports, large drift artefacts)
  gain a durable, encrypted, off-repository backup path with programmatic restore
- the backup-coverage assertion ledger (ADR 0271) gains a Restic-backed entry for
  configuration and state artefacts, closing a gap in the platform's backup
  coverage map
- MinIO Object Lock prevents accidental or malicious deletion of backup snapshots
  during the retention window
- the `restic check` verify step makes restore-readiness provable without a full
  restore dry-run every time

**Negative / Trade-offs**

- Restic's deduplication is single-repository; the MinIO bucket is the only copy;
  the platform should add a second Restic repository pointing to an off-site
  storage provider in a future ADR if the business requires geographic redundancy
- the OpenBao password dependency means Restic cannot restore if OpenBao is
  unavailable; the password must also exist in the break-glass envelope (ADR 0051)
- MinIO Object Lock in GOVERNANCE mode still allows an operator with the correct
  IAM role to delete snapshots; COMPLIANCE mode would prevent this but requires
  Wasabi or a dedicated MinIO instance with retention enforcement

## Boundaries

- Restic covers platform configuration and state artefacts at the file level; it
  does not replace PBS VM snapshots or PostgreSQL dumps for application data
- Restic does not back up the Git repository itself; Gitea's built-in repository
  mirroring and PBS VM snapshot cover that
- Restic does not encrypt MinIO at rest independently; MinIO server-side
  encryption is the at-rest layer; Restic encryption provides the end-to-end
  confidentiality layer on top

## Related ADRs

- ADR 0029: Dedicated backup VM with PBS
- ADR 0034: Controller-local secret manifest and preflight
- ADR 0043: OpenBao for secrets transit and dynamic credentials
- ADR 0051: Control plane backup recovery and break-glass
- ADR 0271: Backup coverage assertion ledger and backup-of-backup policy
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0276: NATS JetStream as the platform event bus
- ADR 0297: Renovate Bot as the automated stack version upgrade proposer
- ADR 0298: Syft and Grype for SBOM and CVE scanning
- ADR 0299: Ntfy as the push notification channel

## References

- <https://github.com/restic/restic>
