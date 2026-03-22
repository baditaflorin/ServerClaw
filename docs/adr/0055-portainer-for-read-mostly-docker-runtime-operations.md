# ADR 0055: Portainer For Read-Mostly Docker Runtime Operations

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The Docker runtime VM is intentionally repo-managed, but there is still no visual console for:

- container health and restart state
- stack status at a glance
- container logs during triage
- bounded emergency actions such as restart or scale-down

Raw Docker CLI access remains useful, but it is not the best default experience for humans or agents that need quick runtime inspection.

## Decision

We will add Portainer as a read-mostly operations console for the Docker runtime boundary.

Steady-state expectations:

1. Portainer is used primarily for inspection, logs, health, and bounded runtime actions.
2. Compose files and repo automation remain the source of truth for desired state.
3. UI-authored stack drift is treated as an exception path and must be documented immediately if used.
4. Access is limited to approved operator and agent identities with scoped roles.

Initial scope:

- `docker-runtime-lv3`
- repo-managed Compose stacks
- container logs and restart history
- emergency restart and pause operations for approved identities

## Consequences

- Operators gain a visual runtime console without abandoning the repo-first delivery model.
- Agents can query or invoke narrow runtime actions through a governed surface instead of broad Docker shell access.
- Runtime drift risk increases if Portainer permissions are too broad.
- Role design and evidence expectations need to be explicit before live rollout.

## Boundaries

- Portainer must not become the primary place where stacks are designed or edited.
- Break-glass UI changes do not replace receipts, runbooks, or repo changes.
- Administrative publication follows the private-first API and operator-surface rules.
