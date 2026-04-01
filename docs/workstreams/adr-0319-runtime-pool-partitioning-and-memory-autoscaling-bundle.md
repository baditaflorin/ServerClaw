# Workstream ADR 0319: Runtime Pool Partitioning And Memory-Aware Autoscaling Bundle

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md), [ADR 0321](../adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md), [ADR 0322](../adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md), [ADR 0323](../adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md)
- Title: Five ADRs to split the overloaded shared runtime into smaller pool-scoped lanes, increase governed memory headroom, and add bounded autoscaling under memory pressure
- Status: merged
- Implemented In Repo Version: 0.177.130
- Live Applied In Platform Version: N/A
- Implemented On: 2026-04-01
- Live Applied On: N/A
- Branch: `codex/adr-0319-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0319-runtime-cells/.worktrees/adr-0319-main-integration`
- Owner: codex
- Depends On: `adr-0105-platform-capacity-model`, `adr-0154-vm-scoped-parallel-execution-lanes`, `adr-0157-per-vm-concurrency-budget-and-resource-reservation`, `adr-0184-failure-domain-labels-and-anti-affinity-policy`, `adr-0192-separate-capacity-classes-for-standby-recovery-and-preview-workloads`, `adr-0214-production-and-staging-cells-as-the-unit-of-high-availability`, `adr-0232-nomad-for-durable-batch-and-long-running-internal-jobs`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/adr-0319-runtime-pool-partitioning-and-memory-autoscaling-bundle.md`, `docs/adr/0319-runtime-pools-as-the-service-partition-boundary.md`, `docs/adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md`, `docs/adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md`, `docs/adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md`, `docs/adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md`, `docs/adr/.index.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`

## Scope

- add a coherent five-ADR architecture bundle for splitting more than 50 repo-managed services away from one overloaded shared runtime lane
- define runtime pools as the next partition boundary inside the existing environment cell model
- define pool-scoped deployment surfaces so agents can change one runtime pool without blocking unrelated work on another
- define an explicit runtime memory increase, host free-memory floor, and autoscaling bounds for elastic pools
- define mobility tiers and migration waves so the current `docker-runtime-lv3` catch-all host can be decomposed safely rather than all at once
- refine the bundle so it points at battle-tested API-first OSS building blocks instead of leaving the implementation path overly custom

## Non-Goals

- claiming any live topology change, VM resize, or autoscaler implementation in this workstream
- replacing Proxmox, Docker Compose, Coolify, or Nomad in one architectural sweep
- pretending every current platform service is equally movable or equally safe to autoscale

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/adr-0319-runtime-pool-partitioning-and-memory-autoscaling-bundle.md`
- `docs/adr/0319-runtime-pools-as-the-service-partition-boundary.md`
- `docs/adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md`
- `docs/adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md`
- `docs/adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md`
- `docs/adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md`
- `docs/adr/.index.yaml`

## Expected Live Surfaces

- none; this is a repo-only architecture bundle

## Selected Defaults

- split the current overloaded shared runtime into multiple runtime pools instead of one larger catch-all VM
- make the runtime pool, not the full environment cell, the default lane for service-level deploy and repair work
- raise the governed runtime memory budget from one shared envelope to pool-specific envelopes with one host-side free-memory floor
- autoscale only elastic pools and only inside declared min and max bounds
- move services in waves according to mobility tier rather than treating stateful anchors and bursty stateless workers the same
- prefer `Nomad`, `Nomad Autoscaler`, `Traefik`, `Dapr`, and `Microcks` before introducing new repo-local runtime orchestration code

## Verification Plan

- regenerate the ADR index after the five new ADRs land
- validate `workstreams.yaml` and the agent-standards gate from this worktree
- perform the final merge-to-main integration step separately so release files and generated truth stay honest

## Merge Criteria

- the five ADRs must read as one runtime-partitioning bundle, not five disconnected suggestions
- the bundle must extend existing capacity, concurrency, failure-domain, and environment-cell ADRs instead of replacing them
- the merge must stay repo-only and must not claim live implementation or a platform-version bump

## Notes For The Next Assistant

- implement ADR 0319 and ADR 0320 together first so the new pool boundary and the new deployment boundary arrive together
- do ADR 0321 before ADR 0322 so autoscaling consumes governed memory envelopes instead of inventing its own
- use ADR 0323 to decide which current `docker-runtime-lv3` services are safe first movers versus anchors that must stay fixed until later
