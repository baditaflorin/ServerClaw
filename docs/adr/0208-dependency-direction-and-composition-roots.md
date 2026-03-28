# ADR 0208: Dependency Direction And Composition Roots

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.40
- Implemented In Platform Version: not applicable (repository-only)
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

As repositories grow, convenience imports accumulate. Helpers start importing
delivery code. Adapters import each other directly. Runtime wiring spreads
across scripts. Once that happens, architecture is no longer clean even if the
repo still talks about interfaces.

Without a dependency rule:

- refactors become risky because concerns are tangled
- tests drag in more runtime than they should
- a provider or delivery surface can end up shaping the domain model

## Decision

We will enforce a dependency rule with explicit composition roots.

The intended direction is:

- domain rules know nothing about delivery mechanisms or concrete providers
- application or use-case services depend inward on domain rules and outward on
  ports
- adapters implement ports and translate to external systems
- delivery layers such as CLI commands, APIs, playbook wrappers, and workflow
  entrypoints call application services
- composition roots wire concrete adapters to ports for a specific runtime

No shared logic may bypass the composition root to instantiate a concrete
provider directly unless that code itself is the composition root.

## Consequences

**Positive**

- refactors inside one layer are less likely to ripple across the whole repo
- product changes stay near the composition root and adapter edges
- tests can run narrower slices with clearer boundaries

**Negative / Trade-offs**

- wiring code becomes more explicit and sometimes more verbose
- existing mixed-layer modules will need incremental untangling

## Boundaries

- This ADR is a target architecture for new work and opportunistic refactors; it
  does not require immediate directory upheaval across the whole repo.
- Generic utility functions are allowed across layers only when they are truly
  generic and do not pull outward dependencies inward.
- A composition root may be a script, a CLI command, a workflow entry, or
  another runtime entrypoint, but it must be easy to locate.

## Related ADRs

- ADR 0062: Ansible role composability and DRY defaults
- ADR 0079: Playbook decomposition by concern
- ADR 0156: Agent session workspace isolation
- ADR 0175: Cross-workstream interface contracts
