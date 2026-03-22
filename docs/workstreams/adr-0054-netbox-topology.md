# Workstream ADR 0054: NetBox For Topology, IPAM, And Inventory

- ADR: [ADR 0054](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0054-netbox-for-topology-ipam-and-inventory.md)
- Title: Visual infrastructure inventory and IPAM plane
- Status: ready
- Branch: `codex/adr-0054-netbox-topology`
- Worktree: `../proxmox_florin_server-netbox-topology`
- Owner: codex
- Depends On: none
- Conflicts With: none
- Shared Surfaces: topology catalog, VM inventory, IP addressing, ownership metadata

## Scope

- choose NetBox for visual topology and IPAM
- define repo-sync and ownership boundaries
- expose structured infrastructure metadata for humans and agents

## Non-Goals

- turning NetBox into an unsupervised mutation surface
- replacing canonical repo documents with free-form UI edits

## Expected Repo Surfaces

- `docs/adr/0054-netbox-for-topology-ipam-and-inventory.md`
- `docs/workstreams/adr-0054-netbox-topology.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a private NetBox deployment
- synchronized site, host, VM, and network inventory views

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0054-netbox-for-topology-ipam-and-inventory.md`

## Merge Criteria

- the ADR makes the source-of-truth boundary explicit
- topology, IPAM, and ownership scope are clearly defined

## Notes For The Next Assistant

- keep repo-to-NetBox synchronization narrower than full bidirectional sync at first
