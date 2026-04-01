# Workstream WS-0329: Runtime Pool Library-Fit Refinement

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md), [ADR 0321](../adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md), [ADR 0322](../adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md), [ADR 0323](../adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md)
- Title: Refine the runtime-pool ADR bundle with battle-tested API-first OSS adoption guidance
- Status: in_progress
- Implemented In Repo Version: pending
- Live Applied In Platform Version: N/A
- Implemented On: pending
- Live Applied On: N/A
- Branch: `codex/adr-0319-library-fit`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0319-library-fit`
- Owner: codex
- Depends On: `adr-0319-runtime-pools-as-the-service-partition-boundary`, `adr-0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes`, `adr-0321-runtime-pool-memory-envelopes-and-reserved-host-headroom`, `adr-0322-memory-pressure-autoscaling-for-elastic-runtime-pools`, `adr-0323-service-mobility-tiers-and-migration-waves-for-runtime-pools`
- Conflicts With: none

## Scope

- refine ADRs 0319 through 0323 so they point to concrete API-first OSS instead of leaving the implementation path overly custom
- name the preferred first-fit products for scheduling, autoscaling, routing, service invocation, contract testing, authorization, orchestration, and messaging
- keep the existing runtime-pool direction while making the next implementation slice easier for future agents to research from upstream docs

## Non-Goals

- replacing the runtime-pool direction accepted in the prior bundle
- claiming live adoption of any new runtime product
- adding service catalogs, playbooks, or automation for these products in this workstream

## Selected Defaults

- `Nomad` stays the preferred pool scheduler direction
- `Nomad Autoscaler` becomes the preferred first autoscaling controller
- `Traefik` becomes the preferred dynamic pool-routing layer
- `Dapr` becomes the preferred service-invocation and integration primitive when apps need those patterns
- `Microcks` becomes the preferred API mock and contract-testing surface
- `OpenFGA`, `Temporal`, and `NATS JetStream` are called out as preferred reuse points for authz, durable orchestration, and messaging

## Verification Plan

- regenerate the ADR index
- run `./scripts/validate_repo.sh agent-standards`
- keep release and generated truth updates for the later integration step if this workstream is merged
