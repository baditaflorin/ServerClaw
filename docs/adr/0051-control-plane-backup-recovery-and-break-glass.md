# ADR 0051: Control-Plane Backup, Recovery, And Break-Glass

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.63.0
- Implemented In Platform Version: 0.33.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The platform already has backup architecture work under ADR 0020 and ADR 0029, but the next control-plane components raise a different kind of recovery risk.

Losing one VM is bad. Losing the state for:

- certificate authorities
- secret authorities
- workflow history and definitions
- notification credentials
- break-glass metadata

can lock operators and agents out of the system entirely.

## Decision

We will treat control-plane state as a distinct backup and recovery concern.

Control-plane state includes at least:

- `step-ca` configuration, root or intermediate material, and trust metadata
- OpenBao storage, recovery material, and auth configuration
- Windmill metadata and database state
- mail-platform sender profiles and related secret references
- repo-side manifests and controller-local recovery references needed to reconnect

Recovery policy:

1. back up control-plane state on a schedule aligned with secret and certificate churn
2. keep at least one recovery path that does not depend on the failed component itself
3. document break-glass entry for loss of routine automation paths
4. run restore drills on a recurring basis instead of assuming backups are valid

## Consequences

- New control-plane apps cannot be adopted without an exit plan.
- Backup scope becomes more explicit than "the VM is backed up."
- Break-glass stops being a vague promise and becomes part of the architecture.

## Implementation Notes

- The repo now exposes a dedicated recovery workflow through [playbooks/control-plane-recovery.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/control-plane-recovery.yml), [roles/control_plane_recovery](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/control_plane_recovery), [roles/control_plane_recovery_store](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/control_plane_recovery_store), [roles/control_plane_recovery_controller](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/control_plane_recovery_controller), and [roles/control_plane_recovery_firewall](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/control_plane_recovery_firewall).
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json) now registers `converge-control-plane-recovery` as the canonical entry point for the scheduled exports, controller bundle refresh, and restore drill.
- The backup-store contract now explicitly includes the `backup-lv3` guest-firewall allowance required for `docker-runtime-lv3` to push the archived control-plane bundles over SSH.
- [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json) now records the generated runtime backup SSH key and controller recovery bundle alongside the pre-existing control-plane bootstrap artifacts.
- Operator procedure is documented in [docs/runbooks/configure-control-plane-recovery.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-control-plane-recovery.md).
- Live application from the 0.63.0 integration release on 2026-03-22 verified scheduled runtime archives for `step-ca`, OpenBao, Windmill, and the mail platform on `backup-lv3`, plus a passing restore drill against the mirrored controller recovery bundle.
