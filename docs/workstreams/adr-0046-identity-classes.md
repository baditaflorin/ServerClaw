# Workstream ADR 0046: Identity Classes For Humans, Services, And Agents

- ADR: [ADR 0046](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0046-identity-classes-for-humans-services-and-agents.md)
- Title: Identity taxonomy for operators, services, agents, and break-glass
- Status: merged
- Branch: `codex/adr-0046-identity-classes`
- Worktree: `../proxmox_florin_server-identity-classes`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: SSH users, API principals, workflow identities, mail senders

## Scope

- define the identity classes used across the platform
- remove ambiguity around human, service, agent, and break-glass credentials
- give future access reviews a stable vocabulary

## Non-Goals

- rotating every existing identity in this planning workstream
- creating a new identity provider by itself

## Expected Repo Surfaces

- `docs/adr/0046-identity-classes-for-humans-services-and-agents.md`
- `docs/workstreams/adr-0046-identity-classes.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- consistent naming and scoping rules across future credentials
- clearer ownership for human, service, and agent access

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0046-identity-classes-for-humans-services-and-agents.md`

## Merge Criteria

- the ADR defines the four identity classes and required metadata
- the workstream records where the taxonomy affects future integrations

## Notes For The Next Assistant

- use this taxonomy when naming future API users, mail senders, and workflow principals
