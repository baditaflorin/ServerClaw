# ADR 0207: Anti-Corruption Layers At Provider Boundaries

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.38
- Implemented In Platform Version: 0.130.38
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

Even with adapters, a platform can still become vendor-shaped if raw provider
payloads, IDs, timestamps, error codes, and event names are allowed to travel
unchanged into shared logic, receipts, or docs.

That is how lock-in quietly grows:

- provider field names become de facto internal schema
- product-specific errors start driving core control flow
- migration work has to untangle years of leaked assumptions

## Decision

Every critical external integration must define an anti-corruption layer at the
provider boundary.

That layer is responsible for translating:

- provider payloads into canonical internal models
- provider errors into canonical internal error classes or envelopes
- provider event names into internal event taxonomy
- provider identifiers into stable internal references where possible

The translation happens once at the boundary. Internal code, stored receipts,
generated docs, and cross-component contracts should consume the normalized
representation instead of raw provider payloads.

## Consequences

**Positive**

- internal models stay stable while providers evolve
- observability and incident handling can use one error and event vocabulary
- provider replacement becomes a boundary refactor instead of a repo-wide
  schema migration

**Negative / Trade-offs**

- translation code must be maintained alongside each adapter
- some provider-specific nuance may need an explicit extension field when it is
  genuinely valuable

## Boundaries

- This ADR does not ban keeping raw provider payloads for debugging, but those
  payloads must stay edge-local and clearly marked as non-canonical.
- The anti-corruption layer does not replace the adapter; it is part of the
  adapter boundary.
- If internal workflows branch on a provider-specific field name, this ADR is
  being violated even if the code sits near an integration package.

## Related ADRs

- ADR 0124: Platform event taxonomy
- ADR 0134: Changelog redaction
- ADR 0166: Canonical error response format and error code registry
- ADR 0169: Structured log field contract
