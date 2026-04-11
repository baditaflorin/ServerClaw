# ADR 0272: Restore Readiness Ladders And Stateful Warm-Up Verification Profiles

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.75
- Implemented In Platform Version: 0.130.51
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

Restore rehearsal evidence shows that a restored VM can clear one low-level
step and still be unusable:

- SSH may never become ready
- HTTP probes may see connection refused or connection reset
- secret stores may come back sealed
- leader-dependent applications may need extra warm-up before synthetic replay

The current restore checks are valuable, but they need a more explicit staged
model for stateful systems.

## Decision

We will verify restores through **readiness ladders** and
**stateful warm-up profiles**.

### Required ladder stages

- restore completed
- guest boot completed
- guest access path ready
- network and dependency path ready
- service-specific warm-up completed
- synthetic replay window passed

### Warm-up profile rules

- each protected service class must declare its own warm-up and recovery
  profile
- sealed, leader-elected, or delayed-start services may not be judged by the
  same first-probe timing as stateless HTTP services
- restore receipts must record the highest completed ladder stage, not only a
  final pass or fail

## Consequences

**Positive**

- restore failures become more diagnosable and less binary
- stateful services get honest verification windows instead of premature red
  noise
- replay evidence becomes more useful for recovery planning

**Negative / Trade-offs**

- restore workflows become longer and more model-heavy
- service teams must maintain warm-up profiles as applications evolve

## Boundaries

- This ADR governs restore verification semantics after backup selection.
- It does not replace backup coverage policy or general production health
  semantics.

## Live Apply Notes

- The governed profile catalog now drives restore-readiness budgets for the
  protected service classes, so restore receipts record the highest completed
  stage, the warm-up attempts used, and whether synthetic replay was eligible.
- The exact-main replay recorded in
  `receipts/restore-verifications/2026-03-29.json` verified the new semantics
  on the live platform from the newest `origin/main` baseline: `postgres`
  failed at `restore_completed` during the PBS restore step,
  `docker-runtime` failed at `restore_completed` during `pbs-restore`, and
  `backup` failed at `restore_completed` because no PBS backups were
  available for selection.
- The canonical integrated live-apply evidence is
  `receipts/live-applies/2026-03-29-adr-0272-restore-readiness-mainline-live-apply.json`,
  which records the latest-main replay, the repo validation sweep, and the
  post-run cleanup proof for the temporary restore VMIDs.

## Related ADRs

- ADR 0099: Automated backup restore verification
- ADR 0188: Failover rehearsal gate for redundancy tiers
- ADR 0190: Synthetic transaction replay for capacity and recovery validation
- ADR 0246: Startup, readiness, liveness, and degraded-state semantics
- ADR 0251: Stage-scoped smoke suites and promotion gates
