# Workstream ADR 0057: Mattermost For ChatOps And Operator-Agent Collaboration

- ADR: [ADR 0057](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0057-mattermost-for-chatops-and-operator-agent-collaboration.md)
- Title: Shared operator and agent collaboration surface
- Status: live_applied
- Branch: `codex/adr-0057-mattermost-chatops`
- Worktree: `../proxmox-host_server-mattermost-chatops`
- Owner: codex
- Depends On: `adr-0045-communication-lanes`, `adr-0050-notification-profiles`
- Conflicts With: none
- Shared Surfaces: `docker-runtime`, `postgres`, collaboration channels, incoming webhooks

## Scope

- choose Mattermost for private ChatOps and collaboration
- define alert-routing, approval, and webhook-driven automation boundaries
- create one shared inbox for operator and agent operations

## Non-Goals

- treating chat messages as the source of truth for infra state
- moving every workflow into chat commands

## Expected Repo Surfaces

- `docs/adr/0057-mattermost-for-chatops-and-operator-agent-collaboration.md`
- `docs/workstreams/adr-0057-mattermost-chatops.md`
- `docs/runbooks/configure-mattermost.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `playbooks/mattermost.yml`
- `roles/mattermost_postgres/`
- `roles/mattermost_runtime/`
- `roles/monitoring_mattermost_notifications/`
- `config/controller-local-secrets.json`
- `config/control-plane-lanes.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `workstreams.yaml`

## Expected Live Surfaces

- private chat workspace for ops traffic
- routed notifications and governed webhook interactions
- Tailscale-only Mattermost entrypoint on the Proxmox host
- seeded collaboration channels and incoming webhooks
- Grafana contact point for Mattermost alert routing

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0057-mattermost-for-chatops-and-operator-agent-collaboration.md`
- `make syntax-check-mattermost`
- `make converge-mattermost`
- `curl -s http://100.118.189.95:8066/api/v4/system/ping`
- `make validate`

## Merge Criteria

- the repo-managed Mattermost converge path applies cleanly from `main`
- private operator access, seeded collaboration channels, incoming webhook routing, and Grafana alert delivery are verified live

## Notes For The Next Assistant

- keep the first rollout private and channel-driven rather than overly ambitious with slash-command automation
- shared SSO remains a follow-on integration under ADR 0056 and does not block the private-first Mattermost rollout
