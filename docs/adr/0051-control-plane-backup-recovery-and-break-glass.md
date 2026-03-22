# ADR 0051: Control-Plane Backup, Recovery, And Break-Glass

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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

