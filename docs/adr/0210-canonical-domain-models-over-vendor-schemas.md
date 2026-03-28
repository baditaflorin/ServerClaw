# ADR 0210: Canonical Domain Models Over Vendor Schemas

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.35
- Implemented In Platform Version: 0.130.37
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

Vendor APIs, UI exports, and product configuration formats are designed around
their own priorities, not around this platform's long-term domain language.

If repo-managed data models mirror those schemas directly:

- product terms become internal truth
- changing provider means reshaping stored data and generated artifacts
- cross-surface reasoning gets harder because each capability speaks a
  different dialect

## Decision

The repository will prefer canonical domain models over vendor-native schemas
for shared internal state.

Canonical models should represent platform meaning first, for example:

- service identity
- publication intent
- secret rotation policy
- backup policy
- identity mapping
- recovery capability

Adapters may keep provider-specific extension fields at the edge, but shared
contracts, generated docs, receipts, and cross-component interfaces should
reference the canonical model whenever practical.

## Consequences

**Positive**

- platform meaning stays stable while implementations change
- shared automation can reason about one internal model instead of many product
  payloads
- provider replacement becomes a mapping problem more often than a data-shape
  rewrite

**Negative / Trade-offs**

- canonical modeling takes design effort and sometimes requires richer
  translation code
- there is a risk of over-modeling if the internal schema grows without clear
  business need

## Boundaries

- This ADR does not forbid storing raw provider exports for debugging or audit,
  but those exports are not the canonical contract.
- Vendor extensions are allowed when there is no clean common denominator, but
  they must stay optional and edge-local.
- Not every temporary script needs a domain model; this applies to shared,
  durable, or cross-surface data.

## Related ADRs

- ADR 0063: Platform vars library
- ADR 0075: Service capability catalog
- ADR 0132: Self-describing platform manifest
- ADR 0166: Canonical configuration locations
