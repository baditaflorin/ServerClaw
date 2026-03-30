# ADR 0267: Expiring Gate Bypass Waivers With Structured Reason Codes

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.104
- Implemented In Platform Version: 0.130.70
- Implemented On: 2026-03-30
- Date: 2026-03-28

## Context

The repository contains many gate-bypass receipts, and a meaningful slice of
them do not describe the failure precisely enough to support systemic cleanup.
That weakens learning, normalizes repeated bypasses, and hides whether the team
used strong substitute evidence or simply forced a push through.

The platform needs bypasses to remain possible, but only as governed exceptions
that actively drive remediation.

## Decision

We will treat every gate bypass as an **expiring waiver** with a structured
reason code and explicit substitute evidence.

### Required waiver fields

- reason code from a controlled taxonomy
- human-readable detail
- impacted validation lanes
- substitute validations that passed
- owner and expiry date
- linked remediation workstream or issue

### Governance rules

- a waiver without a reason code is invalid
- a waiver without substitute evidence is invalid
- repeated waivers with the same reason code past their expiry must escalate
  from warning to release blocker
- release tooling must summarize open waivers and aging repeated reasons

## Consequences

**Positive**

- bypasses stay possible without becoming silent policy erosion
- repeated failure classes become measurable backlog instead of folklore
- good cases are preserved as named substitute evidence, not hidden in chat

**Negative / Trade-offs**

- emergency pushes require more disciplined paperwork
- some low-risk exceptions will feel slower until the taxonomy matures

## Boundaries

- This ADR governs bypass recording and expiry, not the underlying gate lanes.
- It does not replace incident management or mutation-audit evidence.

## Related ADRs

- ADR 0036: Live-apply receipts and verification evidence
- ADR 0048: Command catalog and approval gates
- ADR 0087: Repository validation gate
- ADR 0230: Policy decisions via Open Policy Agent and Conftest
