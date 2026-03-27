# ADR 0178: Dependency Wave Manifests for Parallel Apply

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.176.1
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Date: 2026-03-26

## Context

Parallel execution is not only about "what can run together"; it is also about "what must finish first." The platform has real dependencies:

- network and identity foundations should settle before app rollouts
- secret stores should be available before services consume new credentials
- monitoring and backup changes often trail the services they observe

Without a shared model, operators and agents either over-serialize everything or attempt unsafe parallel applies based on local intuition.

## Decision

We will represent every multi-step rollout as a **dependency wave manifest**. A wave is a set of changes that may run in parallel. Waves themselves execute in order.

### Manifest shape

```yaml
plan_id: tailscale-monitoring-wave-01
waves:
  - wave_id: foundation
    parallel:
      - playbooks/guest-network-policy.yml
      - playbooks/groups/security.yml

  - wave_id: control_plane
    depends_on:
      - foundation
    parallel:
      - playbooks/step-ca.yml
      - playbooks/openbao.yml

  - wave_id: services
    depends_on:
      - control_plane
    parallel:
      - playbooks/monitoring-stack.yml
      - playbooks/uptime-kuma.yml
```

### Execution rule

- all items inside one wave must pass shard and lock checks before starting
- wave `N+1` cannot start until wave `N` is complete or explicitly marked partial-safe
- failed items generate a replan rather than blind continuation

### Review surface

Wave manifests are part of the change review. They make the intended parallelism explicit before any live apply begins.

## Consequences

**Positive**

- Agents can safely parallelize inside known-good boundaries.
- Rollouts become easier to review because ordering is documented instead of implied.
- Failed applies are easier to resume from the last completed wave.

**Negative / Trade-offs**

- Someone must maintain the dependency graph.
- Some work that feels independent at the file level may still need to wait because of operational dependencies.

## Boundaries

- A wave manifest is not a replacement for runtime conflict detection; it is the planned ordering layer above it.
- Single-play changes do not need a multi-wave plan unless they touch shared or platform-scoped surfaces.

## Related ADRs

- ADR 0112: Deterministic goal compiler
- ADR 0154: VM-scoped parallel execution lanes
- ADR 0160: Parallel dry-run fan-out for intent batch validation
- ADR 0176: Inventory sharding and host-scoped ansible execution
- ADR 0182: Live apply merge train and rollback bundle
