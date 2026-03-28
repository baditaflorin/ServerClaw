# ADR 0209: Use-Case Services And Thin Delivery Adapters

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The same platform intent is often exposed through more than one delivery path:
CLI, API, runbook automation, scheduled workflow, or playbook wrapper.

When each entrypoint re-implements its own orchestration, DRY breaks down:

- the same decision logic appears in several places
- one surface gets fixed while another silently drifts
- swapping delivery technology becomes harder because business flow is embedded
  in the transport layer

## Decision

When a platform capability is exposed through multiple delivery surfaces, the
shared orchestration must live in a single use-case service rather than being
copied into each entrypoint.

Thin delivery adapters are responsible only for:

- parsing incoming input
- invoking the relevant use-case service
- translating the result into transport-specific output
- applying transport-local authentication and formatting concerns

Business rules, sequencing, approval decisions, and provider selection belong
inside the use-case service or the domain layer behind it.

## Consequences

**Positive**

- the same behavior can be offered through CLI, API, or workflow without
  recoding the core logic
- bug fixes land once instead of being replayed per surface
- transport changes are less likely to change business outcomes

**Negative / Trade-offs**

- some existing scripts and playbooks will need extraction work to become thin
  adapters
- teams must resist the temptation to place "just one more" rule in a wrapper
  because it feels convenient

## Boundaries

- This ADR does not require every Ansible task to call into Python. It applies
  when orchestration is duplicated across delivery surfaces and needs one
  governed home.
- Thin delivery adapters may still own transport-specific validation and
  rendering.
- A use-case service is not the same thing as a giant god-object; service scope
  should stay capability-focused.

## Related ADRs

- ADR 0048: Command catalog and governed mutation entrypoints
- ADR 0090: Unified platform CLI
- ADR 0129: Runbook automation executor
- ADR 0174: Integration-only canonical truth assembly
