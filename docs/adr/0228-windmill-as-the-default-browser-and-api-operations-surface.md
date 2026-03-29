# ADR 0228: Windmill As The Default Browser-And-API Operations Surface

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.70
- Implemented In Platform Version: 0.130.48
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

ADR 0044 introduced Windmill as an on-platform workflow runtime, but the
platform still has a behavioral gap:

- people design in the repo and then keep operating from a shell
- browser access exists, but it is not yet the default route for routine work
- Codex or local terminals still feel like the operational center of gravity

For production use, the routine operator and agent path should be a durable
server-side surface with logs, approvals, history, and resumability.

## Decision

We will treat **Windmill as the default browser-first and API-first operations
surface** for repeatable tasks.

### Default path rule

If a task is:

- repeatable
- parameterizable
- safe enough to catalog
- valuable to trigger or observe from a browser or API

then it should first become a repo-managed Windmill path before it is treated as
a terminal-first operation.

### Role in the control model

Windmill becomes the primary surface for:

- operator approvals
- browser-triggered routine jobs
- agent-triggered routine jobs
- scheduled and event-driven orchestration that needs state and history
- observation of execution results without live shell attachment

Codex and CLI sessions remain important for design, debugging, and break-glass
work, but they stop being the normal execution home for standard platform
operations.

## Consequences

**Positive**

- Routine operations gain a durable UI and API surface inside the platform.
- Operators can trigger and inspect work without needing a privileged terminal
  session.
- The platform gets closer to "the server runs itself" rather than "the laptop
  is the real control plane".

**Negative / Trade-offs**

- More workflow packaging and governance work is needed up front.
- Windmill becomes even more central and therefore more important to recover
  correctly.

## Boundaries

- Windmill is still the runtime, not the design authority. Logic must return to
  git.
- This ADR does not mean every script belongs in Windmill; narrow host-local
  loops can still live in systemd.

## Related ADRs

- ADR 0044: Windmill for agent and operator workflows
- ADR 0069: Agent tool registry and governed tool calls
- ADR 0119: Budgeted workflow scheduler
- ADR 0129: Runbook automation executor
- ADR 0224: Server-resident operations as the default control model
