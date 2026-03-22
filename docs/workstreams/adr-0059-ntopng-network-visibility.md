# Workstream ADR 0059: ntopng For Private Network Flow Visibility

- ADR: [ADR 0059](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0059-ntopng-for-private-network-flow-visibility.md)
- Title: Visual network-flow analysis for the private guest network
- Status: ready
- Branch: `codex/adr-0059-ntopng-network-visibility`
- Worktree: `../proxmox_florin_server-ntopng-network-visibility`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0012-proxmox-host-bridge-and-nat-network`, `adr-0049-private-api-publication`
- Conflicts With: none
- Shared Surfaces: `vmbr10`, ingress traffic, guest egress, network triage

## Scope

- choose ntopng for network-flow visibility
- define safe collection points and operator access boundaries
- improve triage for private-network incidents and anomalies

## Non-Goals

- packet capture by default
- turning observability tooling into inline network enforcement

## Expected Repo Surfaces

- `docs/adr/0059-ntopng-for-private-network-flow-visibility.md`
- `docs/workstreams/adr-0059-ntopng-network-visibility.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- operator-only network-flow visibility for the private guest network
- recent-history views for incident and capacity analysis

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0059-ntopng-for-private-network-flow-visibility.md`

## Merge Criteria

- the ADR makes data-collection, privacy, and retention boundaries clear
- network-visibility value is specific to the current Proxmox topology

## Notes For The Next Assistant

- prefer flow export or mirrored summaries over heavyweight capture on day one
