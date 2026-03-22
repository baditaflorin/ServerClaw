# ADR 0057: Mattermost For ChatOps And Operator-Agent Collaboration

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The platform can already emit metrics, notifications, and future workflow events, but it does not yet have a shared operational conversation plane for:

- alert acknowledgements
- agent handoffs
- change approvals
- human review of automation output
- one visible inbox for operational chatter and actions

Email alone is too passive and too fragmented for this role.

## Decision

We will use Mattermost as the private ChatOps and operator-agent collaboration surface.

Initial responsibilities:

1. receive alerts and workflow notifications into structured channels
2. host bot users for approved automation and agent handoff patterns
3. provide a shared approval and acknowledgement surface for humans
4. preserve conversation context around incidents and platform changes

Initial integrations:

- Grafana alerts
- Windmill job notifications
- mail platform status and delivery alerts
- future command-approval or workflow-review events

## Consequences

- Operators gain a real-time shared inbox instead of scattered notification paths.
- Agents can present findings, request approval, and hand work back to humans in one governed surface.
- Chat notifications can become noisy if routing and channel ownership are not designed carefully.
- Retention, audit, and bot-permission policies must be explicit.

## Boundaries

- Mattermost is a collaboration surface, not the source of truth for infrastructure state.
- Final decisions still belong in ADRs, runbooks, receipts, and repo-managed automation.
- Sensitive credentials must not be posted into chat instead of stored in approved secret systems.
