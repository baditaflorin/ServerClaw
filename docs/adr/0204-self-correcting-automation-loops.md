# ADR 0204: Self-Correcting Automation Loops

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.37
- Implemented In Platform Version: 0.130.35
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

The repository already records desired state, observed state, validation gates,
and operational receipts, but correction behavior is still fragmented.

Some surfaces retry blindly. Some rely on a human reading a failed receipt and
deciding what to do next. Some can detect drift but do not declare which repair
actions are safe, which actions need approval, or which probe proves the repair
worked.

That leaves three gaps:

- automation cannot correct itself consistently because each workflow invents a
  repair loop ad hoc
- operators cannot tell whether a rerun is a safe reconcile, a destructive
  replacement, or just another opaque retry
- provider-specific failure handling leaks into business logic instead of
  staying behind governed recovery contracts

## Decision

We will treat self-correction as an explicit architecture concern.

Every automation surface that can mutate platform state must declare a
repo-managed correction loop with these parts:

1. the invariant or contract the surface is responsible for keeping true
2. the observation source used to detect deviation from that invariant
3. a diagnosis taxonomy that distinguishes transient failure, contract drift,
   dependency outage, stale input, and irreversible data-loss risk
4. the allowed repair actions in preferred order
5. the verification probe that proves the repair succeeded
6. the escalation path when the loop reaches a safety boundary

Allowed repair actions must prefer the narrowest safe move first:

- no-op with evidence when the desired invariant is already true
- replay or reconcile when the action is idempotent
- bounded rollback when the previous known-good state is recoverable
- human escalation before any destructive action that is not pre-approved by
  contract

Blind retry loops are no longer sufficient architecture. A retry policy may be
one branch inside a correction loop, but it is not the loop itself.

## Consequences

**Positive**

- self-healing behavior becomes reviewable, testable, and reusable
- operators can see whether a workflow is correcting, replacing, or escalating
- repair logic can stay capability-oriented instead of being hard-coded around a
  specific provider's quirks

**Negative / Trade-offs**

- every mutable surface now needs more design metadata up front
- some existing workflows will need refactoring before they can claim
  self-correction honestly

## Boundaries

- This ADR does not permit autonomous destructive recovery outside declared
  contracts and approval rules.
- This ADR does not replace backup, disaster recovery, or break-glass runbooks.
- This ADR governs correction loops for platform automation, not human ad hoc
  troubleshooting notes.

## Related ADRs

- ADR 0064: Health probe contracts
- ADR 0114: Rule-based incident triage engine
- ADR 0170: Platform-wide timeout hierarchy
- ADR 0172: Watchdog escalation and stale job self-healing
