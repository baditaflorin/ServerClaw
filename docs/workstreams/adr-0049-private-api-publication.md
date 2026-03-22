# Workstream ADR 0049: Private-First API Publication Model

- ADR: [ADR 0049](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0049-private-first-api-publication-model.md)
- Title: Publication tiers for internal, operator-only, and public APIs
- Status: merged
- Branch: `codex/adr-0049-private-api-publication`
- Worktree: `../proxmox_florin_server-private-api-publication`
- Owner: codex
- Depends On: `adr-0045-communication-lanes`, `adr-0047-short-lived-creds`
- Conflicts With: none
- Shared Surfaces: NGINX edge, private API listeners, admin surfaces

## Scope

- define publication tiers for APIs
- prevent accidental exposure of internal admin surfaces
- align API exposure with the existing edge and private-network model

## Non-Goals

- publishing new APIs in this planning workstream
- treating every HTTPS endpoint as safe for the public edge

## Expected Repo Surfaces

- `docs/adr/0049-private-first-api-publication-model.md`
- `docs/workstreams/adr-0049-private-api-publication.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- explicit exposure classes for Proxmox, mail, secret, and workflow APIs
- fewer accidentally public admin interfaces

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0049-private-first-api-publication-model.md`

## Merge Criteria

- the ADR defines the three publication tiers and the default rule
- the workstream shows how future API surfaces fit that model

## Notes For The Next Assistant

- keep Proxmox, OpenBao, and CA APIs out of the public edge unless a future ADR says otherwise
