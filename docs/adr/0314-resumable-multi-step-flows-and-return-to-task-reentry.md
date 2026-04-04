# ADR 0314: Resumable Multi-Step Flows And Return-To-Task Reentry

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.5
- Implemented In Platform Version: 0.130.99
- Implemented On: 2026-04-04
- Date: 2026-03-31

## Context

Platform work is interruption-heavy:

- an onboarding flow may pause while waiting for a second factor or an external
  invite acceptance
- a restore, approval, or maintenance action may pause for verification
- an operator may be pulled away by an alert in the middle of a longer task

Today that interruption cost is paid mostly in memory. Users often have to
reconstruct where they were, which data they already entered, and what the next
safe step is.

## Decision

We will treat important multi-step human flows as **resumable tasks** with
explicit return-to-task entry points.

### Resumable flow rules

- long-running or multi-step first-party flows must preserve draft state,
  progress markers, and the last safe resume point
- a returning user should land on a resume summary before the irreversible step,
  not on a blank form or an ambiguous detail page
- the app should clearly separate draft state from committed mutation state

### Reentry rules

- resumable tasks may be reopened from the home surface, the notification
  center, the activity timeline, or a direct deep link
- a resume page must explain what has already happened, what still needs human
  action, and what evidence or diagnostics are available

### Audit rule

Draft preservation is not the same as a mutation. Audit entries are emitted for
committed actions and state transitions, not for every local save.

## Consequences

**Positive**

- interrupted work becomes far less punishing for humans
- onboarding, approval, and recovery flows can continue across sessions without
  guesswork
- the platform starts to feel like one durable application rather than a
  collection of throwaway pages

**Negative / Trade-offs**

- draft persistence and resume semantics add product complexity
- stale drafts must be expired or clearly labeled so they do not mislead users

## Boundaries

- This ADR does not replace backend workflow orchestration engines.
- This ADR governs human-flow durability and reentry, not the underlying worker
  execution semantics.

## Related ADRs

- ADR 0093: Interactive ops portal with live actions
- ADR 0129: Runbook automation
- ADR 0156: Agent session workspace isolation
- ADR 0209: Use-case services and thin delivery adapters
- ADR 0293: Temporal as the durable workflow and task queue engine

## References

- [Runbook Automation](0129-runbook-automation-executor.md)
- [Use-Case Services And Thin Delivery Adapters](0209-use-case-services-and-thin-delivery-adapters.md)
