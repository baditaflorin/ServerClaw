# ADR 0057: Mattermost For ChatOps And Operator-Agent Collaboration

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.57.0
- Implemented In Platform Version: 0.31.0
- Implemented On: 2026-03-22
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
2. expose repo-managed incoming webhook routes for approved automation and agent handoff patterns
3. provide a shared approval and acknowledgement surface for humans
4. preserve conversation context around incidents and platform changes

Initial placement:

- host: `docker-runtime-lv3`
- database: `postgres-lv3`
- exposure: private-only at first, with operator access through the Proxmox host Tailscale proxy on `http://100.118.189.95:8066`

Initial integrations:

- Grafana alerts
- Windmill job notifications
- mail platform status and delivery alerts
- future command-approval or workflow-review events

## Consequences

- Operators gain a real-time shared inbox instead of scattered notification paths.
- Agents can present findings, request approval, and hand work back to humans in one governed surface.
- Chat notifications can become noisy if routing and channel ownership are not designed carefully.
- Retention, audit, and automation-permission policies must be explicit.

## Boundaries

- Mattermost is a collaboration surface, not the source of truth for infrastructure state.
- Final decisions still belong in ADRs, runbooks, receipts, and repo-managed automation.
- Sensitive credentials must not be posted into chat instead of stored in approved secret systems.

## Implementation Notes

- The repo now converges Mattermost through [playbooks/mattermost.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/mattermost.yml), [roles/mattermost_postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/mattermost_postgres), [roles/mattermost_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/mattermost_runtime), and [roles/monitoring_mattermost_notifications](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/monitoring_mattermost_notifications).
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json), [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json), [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/control-plane-lanes.json), and [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json) now record the supported Mattermost workflow, local artifacts, API lane, and webhook lane.
- The initial live rollout is private-first and webhook-driven: the repo seeds the `lv3` team, the managed collaboration channels, the incoming webhook manifest under `.local/mattermost/`, and the Grafana contact point for `platform-alerts`.
- Shared SSO remains follow-on work under ADR 0056 and does not block the private ChatOps surface.
