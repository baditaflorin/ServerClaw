# Workstream ADR 0045: Control-Plane Communication Lanes

- ADR: [ADR 0045](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0045-control-plane-communication-lanes.md)
- Title: Command, API, message, and event lane policy
- Status: merged
- Branch: `codex/adr-0045-communication-lanes`
- Worktree: `../proxmox_florin_server-communication-lanes`
- Owner: codex
- Depends On: `adr-0014-tailscale`, `adr-0041-email-platform`
- Conflicts With: none
- Shared Surfaces: SSH, HTTPS APIs, SMTP submission, webhook flows

## Scope

- define the platform communication lanes
- map secure commands, email send, API access, and webhooks into explicit categories
- document the default transports and trust boundaries for each lane

## Non-Goals

- live protocol rollout in this planning workstream
- adding new public exposure by default

## Expected Repo Surfaces

- `docs/adr/0045-control-plane-communication-lanes.md`
- `docs/workstreams/adr-0045-communication-lanes.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- consistent command, API, message, and event paths across future apps
- fewer one-off control paths and hidden admin channels

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0045-control-plane-communication-lanes.md`

## Merge Criteria

- the ADR clearly maps each communication need into one lane
- the lane boundaries align with the current private-network-first model

## Notes For The Next Assistant

- use this ADR as the framing doc before implementing any new control-plane app
