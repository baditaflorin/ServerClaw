# ADR 0044: Windmill For Agent And Operator Workflows

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository already has controller-side scripts, workflow catalogs, and validation helpers, but it does not yet have a durable on-platform workflow runtime for:

- scheduled automation
- webhook-triggered automation
- API-triggered task execution
- agent-friendly execution endpoints that can be governed separately from direct shell access

Without that layer, the platform remains split between local controller scripts and ad hoc remote commands.

## Decision

We will use Windmill as the first on-platform workflow runtime for agents and operators.

Initial responsibilities:

1. run repo-managed scripts and flows on demand, by schedule, or by API trigger
2. accept internal HTTP routes and webhooks for automation entry points
3. provide a narrow execution plane for routine tasks that do not justify direct SSH
4. integrate with scoped secrets from OpenBao
5. keep execution metadata, run history, and arguments visible to operators

Initial placement:

- host: `docker-runtime-lv3`
- database: `postgres-lv3`
- exposure: private-only at first, with operator access over private networks

## Consequences

- Agentic operations gain a durable API and workflow surface that is not just "SSH and run commands."
- Routine automations can move from workstation-local execution to a stable server-side control plane.
- The repository remains the source of truth for the scripts and flows; Windmill is the runtime, not the design authority.
- Windmill itself becomes critical operational state and must be backed up and restored deliberately.

## Boundaries

- Windmill must not become a place where operators hand-edit business logic that never returns to git.
- Direct root credentials must not be stored inside Windmill.
- Long-lived secrets used by Windmill jobs must be fetched from OpenBao or other approved authorities, not hard-coded in flow definitions.

## Sources

- [What is Windmill?](https://www.windmill.dev/docs/intro)
- [Self-host Windmill](https://www.windmill.dev/docs/advanced/self_host)
- [Triggers](https://www.windmill.dev/docs/getting_started/triggers)
- [HTTP routes](https://www.windmill.dev/docs/core_concepts/http_routing)

