# ADR 0205: Capability Contracts Before Product Selection

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

New initiatives often start with a product name: "use X for identity", "use Y
for object storage", or "switch to Z for workflows". That order makes future
replacement harder because the repo starts encoding vendor vocabulary before it
has written down the actual capability being bought.

When product choice arrives before capability definition:

- provider-specific fields leak into shared config and automation
- later evaluations compare brands instead of requirements
- switching products turns into a cross-repo rewrite instead of an adapter swap

## Decision

We will define the capability contract before selecting or changing a product on
any critical platform surface.

A capability contract must describe at least:

- the capability identifier, such as `identity_provider` or
  `workflow_orchestrator`
- required outcomes and service guarantees
- canonical inputs and outputs
- security and audit expectations
- observability requirements
- portability constraints
- import and export expectations for migration
- failure modes and acceptable degradation behavior

After the capability contract exists, an ADR may choose a product to satisfy it.
The product remains an implementation choice behind that contract, not the
contract itself.

## Consequences

**Positive**

- decisions become easier to revisit because the repo preserves the "why"
  separately from the "which product"
- architecture reviews can compare multiple products against the same contract
- provider replacement becomes bounded by contract compatibility instead of
  discovery-by-code-search

**Negative / Trade-offs**

- capability design adds work before product rollout starts
- existing product-first surfaces will need backfilled contracts over time

## Boundaries

- This ADR does not ban naming products in ADRs; it requires the capability
  contract to exist first.
- This ADR applies to critical shared surfaces, not every one-off local tool.
- A capability contract may still conclude that only one product is currently a
  practical fit; the point is to keep that conclusion reviewable and reversible.

## Related ADRs

- ADR 0030: Role interface contracts and defaults boundaries
- ADR 0075: Service capability catalog
- ADR 0175: Cross-workstream interface contracts
- ADR 0174: Integration-only canonical truth assembly
