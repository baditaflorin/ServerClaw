# Workstream ADR 0057: Mattermost For ChatOps And Operator-Agent Collaboration

- ADR: [ADR 0057](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0057-mattermost-for-chatops-and-operator-agent-collaboration.md)
- Title: Shared operator and agent collaboration surface
- Status: ready
- Branch: `codex/adr-0057-mattermost-chatops`
- Worktree: `../proxmox_florin_server-mattermost-chatops`
- Owner: codex
- Depends On: `adr-0045-communication-lanes`, `adr-0050-notification-profiles`, `adr-0056-keycloak-sso`
- Conflicts With: none
- Shared Surfaces: alerts, workflow notifications, approvals, bot identities

## Scope

- choose Mattermost for private ChatOps and collaboration
- define alert-routing, approval, and bot-identity boundaries
- create one shared inbox for operator and agent operations

## Non-Goals

- treating chat messages as the source of truth for infra state
- moving every workflow into chat commands

## Expected Repo Surfaces

- `docs/adr/0057-mattermost-for-chatops-and-operator-agent-collaboration.md`
- `docs/workstreams/adr-0057-mattermost-chatops.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- private chat workspace for ops traffic
- routed notifications and governed bot interactions

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0057-mattermost-for-chatops-and-operator-agent-collaboration.md`

## Merge Criteria

- the ADR defines how approvals and notifications flow without replacing repo truth
- bot and operator identity boundaries are explicit

## Notes For The Next Assistant

- keep the first rollout private and channel-driven rather than overly ambitious with slash-command automation
