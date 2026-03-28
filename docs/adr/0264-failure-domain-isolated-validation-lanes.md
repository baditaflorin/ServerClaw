# ADR 0264: Failure-Domain-Isolated Validation Lanes

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The receipt trail shows that pushes and integrations repeatedly stalled because
one shared pre-push gate tried to prove too many unrelated things at once.
Changes focused on docs, auth, or one service were blocked by unrelated
`packer`, `ansible-lint`, schema-validation, or generated-surface failures.

That behavior turns one failing subsystem into a platform-wide delivery outage.
It also teaches operators the wrong habit: bypass the whole gate instead of
preserving the parts that still provide signal.

## Decision

We will split repository and promotion validation into **failure-domain-isolated
lanes** that map to the surfaces a change actually touches.

### Mandatory lane model

- each mutable surface class must declare its required validation lanes
- a change must hard-fail only the lanes that protect its owned surfaces plus a
  small set of fast global invariants
- unrelated lanes may report warning or degraded state, but they may not block
  a focused change by default

### Required lane classes

- repository structure and schema lane
- generated artifact and canonical-truth lane
- documentation and ADR lane
- service-specific syntax and unit lane
- remote builder lane
- live-apply and promotion lane

### Good-path requirement

- every lane must emit a reusable green-path evidence summary when it passes
- substitute validations in emergency waivers must reference these focused
  green-path summaries instead of ad hoc prose

## Consequences

**Positive**

- unrelated failures no longer take the whole delivery system down
- focused work keeps strong local guardrails without waiting on distant
  subsystems
- successful targeted validations become first-class reusable evidence

**Negative / Trade-offs**

- lane ownership metadata adds repository complexity
- some cross-cutting bugs may surface later unless the fast global invariants
  stay disciplined

## Boundaries

- This ADR governs validation partitioning and blocking policy.
- It does not define how remote builders are mirrored or how waivers are
  recorded.

## Related ADRs

- ADR 0087: Repository validation gate
- ADR 0160: Parallel dry-run fan-out for intent batch validation
- ADR 0213: Architecture fitness functions in the validation gate
- ADR 0229: Gitea Actions runners for on-platform validation and release
  preparation
