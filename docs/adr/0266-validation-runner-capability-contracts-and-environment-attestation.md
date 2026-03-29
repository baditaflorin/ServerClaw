# ADR 0266: Validation Runner Capability Contracts And Environment Attestation

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Receipt evidence shows repeated validation failures caused by runner conditions:
unreachable build servers, stalled SSH handoffs, unavailable Docker daemons,
architecture mismatches, and cleanup environments that could not complete their
own scratch-space lifecycle.

The gate currently assumes all runners are interchangeable even when their
actual capabilities differ.

## Decision

We will require every local or remote validation runner to publish a
**capability contract** and a per-run **environment attestation**.

### Required capability fields

- CPU architecture and emulation support
- container runtime availability
- git and archive tooling availability
- network reachability class
- scratch-space cleanup guarantees
- supported validation lanes

### Scheduling rules

- a validation lane may run only on runners whose capability contract satisfies
  that lane
- if no compatible runner is available, the lane must fail as `runner_unavailable`
  instead of misreporting a content failure
- build handoff receipts must record the runner identity and attested
  capabilities used for that run

## Consequences

**Positive**

- runner failures become explicit infrastructure signals instead of noisy false
  negatives
- architecture-specific or Docker-dependent work is scheduled deliberately
- handoff problems become easier to reason about historically

**Negative / Trade-offs**

- runner metadata and scheduling logic add coordination overhead
- operators must maintain contracts as the runner fleet evolves

## Boundaries

- This ADR governs runner truth and dispatch eligibility.
- It does not define waiver policy or repository snapshot format.

## Related ADRs

- ADR 0082: Remote build execution gateway
- ADR 0083: Docker-based check runner
- ADR 0163: Platform-wide retry taxonomy and exponential backoff
- ADR 0170: Platform-wide timeout hierarchy
- ADR 0227: Bounded command execution via systemd-run and approved wrappers
