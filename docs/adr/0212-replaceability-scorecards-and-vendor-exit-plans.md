# ADR 0212: Replaceability Scorecards And Vendor Exit Plans

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Avoiding vendor lock-in is not only about coding style. Lock-in usually appears
through missing exit preparation:

- no current export path for data or configuration
- no agreed trigger for when a replacement evaluation should start
- no record of which proprietary features are acceptable and which are too
  expensive to unwind later

Without an exit plan, "we can switch later" is usually wishful thinking.

## Decision

Every critical product ADR must include a replaceability scorecard and a vendor
exit plan.

The scorecard must cover at least:

- contract fit against the capability definition
- data export and import viability
- operational migration complexity
- proprietary surface area and acceptable exceptions
- fallback or downgrade options
- observability and audit continuity during migration

The exit plan must define:

- the trigger conditions for reevaluating the product
- the canonical data and config artifacts that must remain portable
- the minimum migration path to one alternative
- the owner and review cadence for keeping the plan honest

## Consequences

**Positive**

- product selection becomes a reversible investment instead of a permanent bet
- teams are forced to identify portability gaps before they become emergencies
- future migrations can start from a maintained plan instead of fresh panic

**Negative / Trade-offs**

- ADRs for critical products become longer and more demanding
- some product choices may be rejected not because they lack features, but
  because they fail the exit-plan test

## Boundaries

- This ADR does not require two live providers for every capability.
- An explicit exception may still approve a sticky product, but the lock-in must
  be named, justified, and time-bounded.
- Replaceability review is required for critical platform surfaces, not for
  throwaway local utilities.

## Related ADRs

- ADR 0008: Versioning model for repo and host
- ADR 0100: Disaster recovery targets and runbook
- ADR 0205: Capability contracts before product selection
- ADR 0210: Canonical domain models over vendor schemas
