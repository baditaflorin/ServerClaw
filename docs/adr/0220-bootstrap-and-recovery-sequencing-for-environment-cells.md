# ADR 0220: Bootstrap And Recovery Sequencing For Environment Cells

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The platform already has many moving parts, and the number will grow as
staging, replicas, and recovery lanes become more faithful.

Without an agreed sequence, automation tends to discover dependencies the hard
way:

- identity starts before the database is ready
- public ingress comes up before upstream health is meaningful
- restore drills begin before the control plane can verify them
- staging gets built in a different order from production and then stops being a
  trustworthy rehearsal lane

The user request for "init type sequence" is best handled as a clear bootstrap
and recovery phase model.

## Decision

We will define a standard **bootstrap and recovery sequence** for every
environment cell.

### Phases

1. `substrate`: networking, storage attachment, hypervisor or cloud primitives,
   and base OS reachability
2. `bootstrap`: first access, trust anchors, DNS seeds, and inventory truth
3. `control`: identity, secrets, orchestration, service discovery, and policy
   enforcement
4. `state`: primary data systems and their intra-environment replicas
5. `core_workloads`: operator-critical and production-critical application
   runtimes
6. `edge`: ingress, reverse proxy, and public or partner traffic exposure
7. `observability_and_supporting`: metrics, logs, traces, alerting, and
   supporting services
8. `peripheral`: optional, convenience, or experimental services

### Rules

- A phase may depend only on the same phase or an earlier phase.
- Recovery runs in the same order as initial bootstrap.
- Staging must follow the same logical sequence as production even if several
  phases are temporarily hosted on one VM.
- Health gates between phases must be explicit so automation can stop with
  evidence instead of racing onward blindly.

## Consequences

**Positive**

- Bring-up and restore become more repeatable.
- Staging becomes a more trustworthy rehearsal lane because it follows the same
  phase model.
- The platform gains a better boundary between bootstrap concerns and normal
  steady-state operations.

**Negative / Trade-offs**

- Automation will need to encode and validate more dependency metadata.
- Some existing surfaces may reveal hidden circular dependencies that need
  refactoring.

## Boundaries

- This ADR defines the sequence and gating model, not the exact tooling used to
  execute it.
- Emergency break-glass recovery can still violate the preferred phase order,
  but any such action is an exception that must be documented.

## Related ADRs

- ADR 0048: Command catalog and approval model
- ADR 0100: Formal RTO/RPO targets and disaster recovery playbook
- ADR 0172: Watchdog escalation and stale job self-healing
- ADR 0204: Self-correcting automation loops
- ADR 0216: Service criticality rings for foundation, core, supporting, and
  peripheral functions
