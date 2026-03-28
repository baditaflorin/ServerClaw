# ADR 0206: Ports And Adapters For External Integrations

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.34
- Implemented In Platform Version: 0.130.35
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

The platform integrates with many external systems: Proxmox, Hetzner, DNS,
Mail, Keycloak, container registries, and future services. If those
integrations are consumed directly from business logic, the core workflow starts
depending on SDK details, HTTP payloads, and provider-specific error behavior.

That coupling creates two problems:

- swapping a provider becomes a deep rewrite instead of a bounded integration
  change
- tests have to emulate a product API everywhere instead of only at the edge

## Decision

We will use ports and adapters for all critical external integrations.

The architecture rule is:

- application and domain logic depend on ports that express platform intent
- adapters implement those ports for a specific product, protocol, or tool
- concrete wiring happens in a composition root, not in shared business logic

Examples of adapters include:

- a Proxmox adapter behind a VM lifecycle port
- a Keycloak adapter behind an identity-provider port
- an HTTP adapter and a CLI adapter behind the same capability port when both
  are valid implementations

No provider SDK, HTTP client shape, or product-specific CLI invocation may be a
required dependency of shared business logic outside the adapter boundary.

## Consequences

**Positive**

- external products become replaceable in smaller, reviewable slices
- tests can exercise core behavior with fake ports instead of live products
- product-specific complexity stays near the edge where it belongs

**Negative / Trade-offs**

- adapter design can feel slower than direct product calls for one-off work
- there is some unavoidable translation overhead between core logic and products

## Boundaries

- This ADR does not require every shell command to become an interface on day
  one; it applies when a dependency is shared, critical, or expected to be
  replaced.
- Thin wrappers are not enough by themselves. If the core still depends on a
  product payload or SDK type, the port boundary has not been achieved.
- This ADR governs architecture direction for new and refactored surfaces; it
  does not force a big-bang rewrite.

## Related ADRs

- ADR 0039: Shared controller automation toolkit
- ADR 0090: Unified platform CLI
- ADR 0120: Dry-run semantic diff engine
- ADR 0175: Cross-workstream interface contracts
