# Workstream ADR 0050: Transactional Email And Notification Profiles

- ADR: [ADR 0050](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0050-transactional-email-and-notification-profiles.md)
- Title: Mail sender profiles for platform, operators, and agents
- Status: merged
- Branch: `codex/adr-0050-notification-profiles`
- Worktree: `../proxmox_florin_server-notification-profiles`
- Owner: codex
- Depends On: `adr-0041-email-platform`, `adr-0046-identity-classes`
- Conflicts With: none
- Shared Surfaces: Stalwart, SMTP submission, notifications, agent reports

## Scope

- define sender profiles on top of the chosen mail platform
- separate operator, platform, and agent mail identities
- make email send a governed capability instead of a generic SMTP login

## Non-Goals

- live mail-stack deployment in this planning workstream
- replacing ADR 0041

## Expected Repo Surfaces

- `docs/adr/0050-transactional-email-and-notification-profiles.md`
- `docs/workstreams/adr-0050-notification-profiles.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- dedicated sender profiles for alerts, reports, and transactional mail
- clearer audit and revocation paths for outbound mail

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0050-transactional-email-and-notification-profiles.md`

## Merge Criteria

- the ADR defines the initial sender profile set and their required metadata
- the workstream keeps this layered on top of ADR 0041 instead of duplicating it

## Notes For The Next Assistant

- treat Stalwart as the mail substrate and this ADR as the sender-governance layer
