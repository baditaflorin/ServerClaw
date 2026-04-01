# Workstream ws-0324-programmatic-doc-shards: Programmatic Document And Registry Sharding ADR Set

- ADR: [ADR 0324](../adr/0324-service-definition-shards-and-generated-service-catalog-assembly.md)
- Title: Define programmatic sharding patterns for oversized service, ADR, workstream, discovery, and summary surfaces
- Status: merged
- Branch: `codex/ws-0324-programmatic-doc-shards`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0324-programmatic-doc-shards`
- Owner: codex
- Depends On: `ADR 0038`, `ADR 0163`, `ADR 0164`, `ADR 0174`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0324-service-definition-shards-and-generated-service-catalog-assembly.md`, `docs/adr/0325-faceted-adr-index-shards-and-reservation-windows.md`, `docs/adr/0326-workstream-registry-shards-with-active-and-archive-assembly.md`, `docs/adr/0327-sectional-agent-discovery-registries-and-generated-onboarding-packs.md`, `docs/adr/0328-size-budgeted-root-summaries-and-automatic-rollover-ledgers.md`, `docs/adr/.index.yaml`, `docs/workstreams/ws-0324-programmatic-doc-shards.md`, `workstreams.yaml`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`

## Scope

- define a per-service bundle model so service-shaped facts stop accumulating in a few giant aggregate files
- define a faceted ADR discovery and reservation model so a growing ADR corpus stays queryable and parallel-safe
- define active/archive workstream sharding so `workstreams.yaml` stops carrying the full operational history forever
- define sectional discovery registries and size-budgeted root summaries so agent onboarding surfaces stay small enough to read quickly

## Non-Goals

- implementing the sharded layouts or generators in this workstream
- moving any existing service catalog, ADR file, or workstream record to a new location yet
- changing live infrastructure or claiming new platform capabilities

## Reserved ADR Window

- Current latest committed ADR at branch start: `0318`
- Reserved for a parallel future task to avoid collisions: `0319` through `0323`
- This workstream therefore uses: `0324` through `0328`

## Expected Repo Surfaces

- `docs/adr/0324-service-definition-shards-and-generated-service-catalog-assembly.md`
- `docs/adr/0325-faceted-adr-index-shards-and-reservation-windows.md`
- `docs/adr/0326-workstream-registry-shards-with-active-and-archive-assembly.md`
- `docs/adr/0327-sectional-agent-discovery-registries-and-generated-onboarding-packs.md`
- `docs/adr/0328-size-budgeted-root-summaries-and-automatic-rollover-ledgers.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0324-programmatic-doc-shards.md`
- `workstreams.yaml`

## Verification

- `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`
- `scripts/validate_repo.sh agent-standards`
