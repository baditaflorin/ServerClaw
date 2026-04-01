# ADR 0319: Runtime Pools As The Service Partition Boundary

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Date: 2026-04-01

## Context

The platform now carries more than 50 repo-managed services, but a large share
of those services still land on the same shared runtime host:
`docker-runtime-lv3`.

That concentration now hurts both delivery flow and runtime safety:

- ADR 0154 gives us VM-scoped execution lanes, but unrelated services on the
  same runtime VM still serialize against the same lane
- one memory-bursty workload such as notebooks, OCR, retrieval, or AI workers
  can push the whole shared runtime into reclaim pressure
- control-plane anchors such as identity, secrets, workflow dispatch, and
  internal APIs still share failure and restart blast radius with operator UIs,
  collaboration tools, and product applications

The platform already has a good outer boundary in ADR 0214: the environment
cell. What it lacks is a smaller, service-level partition boundary inside one
cell so we can change one cluster of services without implicitly touching every
other service on the same runtime host.

The platform also does not want to grow a bespoke runtime framework when
production-tested OSS already exists and has docs future agents can verify
directly.

## Decision

We will treat the **runtime pool** as the primary partition boundary for
repo-managed services inside one environment cell.

### Runtime pool model

Each environment cell may contain multiple runtime pools. A runtime pool is a
bounded group of one or more runtime VMs that share the same:

- service class
- deploy lane
- memory envelope
- restart and rollback domain
- autoscaling policy

### Minimum pool split for production

Production must converge toward at least these three pools:

- `runtime-control`: identity, secrets, workflow control, message bus, internal
  APIs, and other control-plane anchors
- `runtime-general`: moderate-memory web applications, operator surfaces, and
  stateless platform apps that are not AI-bursty
- `runtime-ai`: memory-bursty inference, retrieval, OCR, notebook, and heavy
  worker services

Dedicated non-pool planes such as `nginx-lv3`, `postgres-lv3`,
`monitoring-lv3`, `docker-build-lv3`, and `coolify-lv3` remain separate from
this runtime-pool split.

### Preferred runtime substrate

The first implementation should prefer existing API-first OSS rather than new
custom orchestration code:

- `Nomad` is the preferred scheduler for runtime pools that outgrow one
  Compose-managed VM and need declarative placement, restart policy, and
  namespace-level isolation
- `Traefik` is the preferred pool ingress and service-discovery layer for
  dynamic routing between pool members
- `Dapr` is the preferred application runtime helper when services need
  service-to-service invocation, pub/sub, state bindings, or workflow helpers
  without bespoke integration glue

This ADR does not require every pool to move to those products immediately, but
it makes them the default direction for new pool-aware implementation work.

### Hard partitioning rules

- control-plane anchors may not share a runtime pool with AI-bursty workloads
- no runtime pool may exceed 15 repo-managed services without an explicit split
  review
- no runtime pool may carry more than 70% steady-state usage of its approved
  baseline memory envelope for more than one review window; sustained excess
  means the pool is under-partitioned
- `docker-runtime-lv3` is now a legacy catch-all that must shrink over time,
  not the permanent home for every new service

## Consequences

**Positive**

- service placement gains a smaller, clearer failure and restart boundary than
  the full environment cell
- unrelated agents can work on different runtime pools without defaulting to
  one shared runtime lane
- memory-heavy AI services stop being the silent default neighbors of the most
  sensitive control-plane services

**Negative / Trade-offs**

- the repository needs more topology metadata than one `docker-runtime-lv3`
  catch-all
- more pools mean more playbooks, probes, and migration planning work
- some current services will need explicit exceptions until the pool split is
  fully implemented
- adopting Nomad, Traefik, and Dapr raises the platform baseline, so partial
  rollouts must avoid leaving operators with three half-integrated runtimes

## Boundaries

- This ADR defines the partition boundary inside one environment cell; it does
  not choose the exact scheduler or autoscaler implementation.
- This ADR does not require every stateful component to move into a runtime
  pool. Dedicated state VMs remain valid.

## Related ADRs

- ADR 0105: Platform capacity model and resource quota enforcement
- ADR 0154: VM-scoped parallel execution lanes
- ADR 0157: Per-VM concurrency budget and resource reservation
- ADR 0184: Failure-domain labels and anti-affinity policy
- ADR 0214: Production and staging cells as the unit of high availability
- ADR 0232: Nomad for durable batch and long-running internal jobs
