# ADR 0262: OpenFGA And Keycloak For Delegated ServerClaw Capability Authorization

- Status: Accepted
- Implementation Status: Live applied and exact-main reverified on workstream branch pending merge-to-main
- Implemented In Repo Version: pending merge-to-main version bump (latest replay baseline 0.177.92)
- Implemented In Platform Version: 0.130.61
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

The repository already has strong identity and approval concepts, but
ServerClaw needs runtime authorization at a more granular level:

- which user owns which workspace
- which assistant may act for which user
- which skill may call which connector
- which connector may read which personal-data scope
- which channel is allowed to send on behalf of which assistant

Existing command approvals and platform policy are necessary but too coarse to
express those subject-resource relationships by themselves.

## Decision

We will use **Keycloak** for authentication and **OpenFGA** for delegated
runtime authorization in ServerClaw.

### Responsibility split

- Keycloak authenticates humans, assistants, services, and browser sessions
- OpenFGA answers relationship-based authorization questions at runtime

### Authorization model

OpenFGA should model at least:

- user to workspace ownership
- workspace to assistant membership
- assistant to skill assignment
- skill to tool and connector grants
- connector to data-plane scope grants
- channel to send-or-receive permissions

### Policy boundary

- OpenFGA governs runtime who-can-do-what relationships
- OPA and existing approval catalogs remain the right place for broader
  platform policy, admission, and approval rules

## Consequences

**Positive**

- ServerClaw can express delegated authority without hard-coding role logic
  everywhere.
- Per-user and per-workspace capability boundaries become reviewable and
  auditable.
- Fine-grained authz stops being an application-specific afterthought.

**Negative / Trade-offs**

- Operators must manage another stateful policy data service and its recovery
  story.
- Authorization modeling discipline is required or the graph will become hard
  to reason about.

## Boundaries

- OpenFGA does not replace Keycloak login, token issuance, or MFA.
- OpenFGA does not replace human approval gates for sensitive live platform
  change.
- This ADR governs ServerClaw runtime authorization, not every current LV3 app.

## Related ADRs

- ADR 0048: Command catalog and approval gates
- ADR 0056: Keycloak for operator and agent SSO
- ADR 0230: Policy decisions via Open Policy Agent and Conftest
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3

## References

- <https://openfga.dev/docs/getting-started/overview>
- <https://openfga.dev/docs/getting-started/tuples-api-best-practices>
