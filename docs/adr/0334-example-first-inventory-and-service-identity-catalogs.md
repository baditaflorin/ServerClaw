# ADR 0334: Example-First Inventory And Service Identity Catalogs

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Date: 2026-04-02
- Tags: inventory, examples, templates, identities, forkability

## Context

The current repo catalogs still reflect one integrated environment in many
places. That is useful for a live deployment, but it is not ideal for a public
template because new users need to understand which values are examples and
which are canonical requirements.

## Decision

Primary onboarding catalogs should move toward example-first inventories and
replaceable service-identity definitions.

### Example-first rule

- committed starter values should be obviously replaceable
- sample hostnames, domains, and service identities should be documented as examples
- fork instructions should begin from examples rather than from one production deployment

### Catalog direction

Likely follow-up surfaces include:

- inventory examples
- example provider profiles
- sample service-publication identities
- sample controller-local manifest layouts

## Consequences

**Positive**

- fresh forks get a clearer first-run path
- public readers can distinguish architecture from one environment's choices
- onboarding becomes more like a product flow and less like archaeology

**Negative / Trade-offs**

- examples must stay synchronized with the real automation contracts
- some current live-truth files may need companion example files to avoid confusion

## Boundaries

- This ADR does not say live catalogs can no longer exist.
- This ADR does not require every current inventory file to become synthetic overnight.

## Related ADRs

- ADR 0033: Declarative service topology catalog
- ADR 0054: NetBox for topology, IPAM, and inventory
- ADR 0333: Private overlay files for deployment-specific secrets and identities
