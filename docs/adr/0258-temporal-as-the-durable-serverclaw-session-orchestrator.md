# ADR 0258: Temporal As The Durable ServerClaw Session Orchestrator

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

ServerClaw sessions need to survive beyond one HTTP request or one chat turn.
They may need to:

- wait for a user reply
- pause for approval
- sleep until a calendar or reminder time
- retry connectors or browser actions
- resume after process restarts

Windmill is the right browser-first operations surface for governed platform
jobs, but it is not the ideal home for thousands of long-lived assistant
conversations with fine-grained signals and timers. Nomad is the right future
scheduler for internal jobs, but it is not a workflow-state engine.

## Decision

We will use **Temporal** as the durable workflow engine for ServerClaw session
orchestration.

### Runtime rule

- one conversation thread or long-lived assistant task maps to a Temporal
  workflow execution
- inbound chat messages, approval decisions, and connector callbacks arrive as
  workflow signals or events
- retries, timers, and resumability are owned by Temporal rather than by chat
  clients or ad hoc database loops

### Boundary rule

- Temporal owns long-lived assistant state progression
- Windmill remains the browser-first operations surface for routine platform
  jobs
- Nomad may later host Temporal workers once ADR 0232 is implemented

## Consequences

**Positive**

- ServerClaw conversations gain durable execution, timers, and resumability.
- Human-in-the-loop pauses stop depending on one container process or one chat
  client staying alive.
- The product gets a workflow runtime built for long waits and repeated signals
  rather than only short jobs.

**Negative / Trade-offs**

- Temporal is a substantial new control-plane dependency.
- Workflow design discipline is required so assistant conversations do not turn
  into opaque monoliths.

## Boundaries

- This ADR governs ServerClaw session orchestration, not every existing LV3
  workflow.
- Temporal does not replace the repo as the design authority or Windmill as the
  primary operator-facing routine-operations surface.

## Related ADRs

- ADR 0044: Windmill for agent and operator workflows
- ADR 0228: Windmill as the default browser-and-api operations surface
- ADR 0232: Nomad for durable batch and long-running internal jobs
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3

## References

- <https://docs.temporal.io/>
- <https://assets.temporal.io/durable-execution.pdf>
