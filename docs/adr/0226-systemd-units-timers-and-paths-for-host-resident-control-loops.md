# ADR 0226: Systemd Units, Timers, And Paths For Host-Resident Control Loops

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.52
- Implemented In Platform Version: 0.130.38
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

Once the platform starts reconciling and supervising itself from inside the
server boundary, it needs a host-native primitive for:

- boot ordering
- process supervision
- scheduled execution
- file or path-triggered execution
- restart and backoff policy

Relying on `cron`, ad hoc shell wrappers, or detached terminal sessions is not a
production-grade answer for those concerns on Debian and Proxmox hosts.

## Decision

We will use **systemd** as the canonical host-resident supervisor for platform
control loops.

### Required unit types

- `*.service` for long-running agents and one-shot control actions
- `*.timer` for scheduled reconciliation and maintenance
- `*.path` for local file-triggered actions such as staged bundle arrival or
  state handoff
- optional `*.socket` units where activation materially reduces idle footprint

### Policy rules

- recurring host-resident automation must use `systemd.timer`, not `cron`
- every long-running host agent must have explicit restart, timeout, and
  dependency semantics
- server-resident control loops must surface their logs through journald and the
  broader observability pipeline
- unit ordering must follow the bootstrap and recovery sequencing defined in ADR
  0220

## Consequences

**Positive**

- Host-local automation gains mature supervision and boot ordering.
- Scheduling and restart behavior become reviewable repository truth.
- The platform uses the operating system's native control plane instead of
  recreating one in shell scripts.

**Negative / Trade-offs**

- Operators need discipline around unit design and not just command lines.
- Some current shell-first flows will need to be recast as services or timers.

## Boundaries

- Systemd is the host supervisor, not the distributed scheduler for every
  future workload.
- This ADR governs host-resident control loops, not every application service in
  the platform.

## Related ADRs

- ADR 0170: Platform-wide timeout hierarchy
- ADR 0204: Self-correcting automation loops
- ADR 0220: Bootstrap and recovery sequencing for environment cells
- ADR 0224: Server-resident operations as the default control model
- ADR 0225: Server-resident reconciliation via Ansible Pull
