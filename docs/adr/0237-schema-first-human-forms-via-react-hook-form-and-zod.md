# ADR 0237: Schema-First Human Forms Via React Hook Form And Zod

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.74
- Implemented In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

Human workflows in this platform regularly ask for structured input:

- operator onboarding and offboarding
- approval forms
- runbook parameters
- maintenance-window creation
- service-specific admin forms

Hand-built form state and copy-pasted validation logic would quickly create UX
drift and inconsistent error handling.

## Decision

We will build first-party structured forms with **React Hook Form** for form
state and **Zod** for schema-driven validation and typing.

### Required form rules

- each non-trivial form must have one authoritative schema definition
- client-side validation should mirror, not replace, server validation
- shared schemas should be reusable in docs, tests, and automation where
  possible
- field-level errors, defaults, touched state, and submit state must be rendered
  consistently

### Why this pair

- React Hook Form keeps form state performant and ergonomic without custom
  reducers
- Zod provides typed schemas that can be shared beyond the view layer
- the resolver bridge avoids page-local validation glue

## Consequences

**Positive**

- human forms become easier to keep DRY and correct
- validation behavior is easier to test and reuse
- future agent and automation surfaces can benefit from the same schema
  definitions without making them the primary audience today

**Negative / Trade-offs**

- teams must maintain schemas deliberately rather than relying on implicit HTML
  validation only
- some legacy forms will need migration work

## Boundaries

- This ADR does not remove the need for authoritative server validation.
- Tiny one-field forms may remain simple native forms when a schema abstraction
  would be heavier than the problem.

## Related ADRs

- ADR 0108: Operator onboarding and offboarding
- ADR 0206: Ports and adapters for external integrations
- ADR 0209: Use-case services and thin delivery adapters
- ADR 0228: Windmill as the default browser and API operations surface

## References

- <https://github.com/react-hook-form/resolvers>
- <https://zod.dev/>
