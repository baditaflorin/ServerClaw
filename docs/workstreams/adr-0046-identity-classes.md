# Workstream ADR 0046: Identity Classes For Humans, Services, And Agents

- ADR: [ADR 0046](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0046-identity-classes-for-humans-services-and-agents.md)
- Title: Identity taxonomy for operators, services, agents, and break-glass
- Status: live_applied
- Branch: `codex/adr-0046-identity-classes`
- Worktree: `../proxmox-host_server-identity-classes`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: SSH users, API principals, workflow identities, mail senders

## Scope

- define the identity classes used across the platform
- remove ambiguity around human, service, agent, and break-glass credentials
- give future access reviews a stable vocabulary
- encode the taxonomy in canonical repository state and validation

## Non-Goals

- rotating every existing identity in this planning workstream
- creating a new identity provider by itself

## Expected Repo Surfaces

- `docs/adr/0046-identity-classes-for-humans-services-and-agents.md`
- `docs/workstreams/adr-0046-identity-classes.md`
- `docs/runbooks/identity-taxonomy-and-managed-principals.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `docs/repository-map.md`
- `docs/assistant-operator-guide.md`
- `scripts/validate_repository_data_models.py`
- `versions/stack.yaml`
- `workstreams.yaml`

## Expected Live Surfaces

- reviewed live principals for the current human, service, agent, and break-glass classes
- consistent naming and scoping rules across current and future credentials
- clearer ownership for Linux access, Proxmox API automation, mail submission, and break-glass recovery

## Verification

- `make validate-data-models`
- `make validate-generated-docs`
- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0046-identity-classes-for-humans-services-and-agents.md`
- verify `ops@pam` TOTP state and `lv3-automation@pve` token inventory on the Proxmox host
- verify `server@example.com` exists in the mail gateway mailbox inventory
- verify the host SSH daemon still keeps `root` in key-only break-glass mode with password auth disabled

## Merge Criteria

- the ADR defines the four identity classes and required metadata
- the taxonomy is represented in canonical state and enforced in validation
- the workstream records where the taxonomy affects future integrations

## Live Apply Notes

- Live apply completed on `2026-03-22` from `main`.
- Verification confirmed `ops` for routine Linux access, `ops@pam` with TOTP for routine Proxmox administration, `lv3-automation@pve` for agent API access, `server@example.com` for the managed mail service identity, and `root` as host-only break-glass.
- The shared bootstrap-key debt between `ops` and `root` remains explicitly tracked in canonical state even though routine operator access now uses short-lived `step-ca` SSH certificates.
