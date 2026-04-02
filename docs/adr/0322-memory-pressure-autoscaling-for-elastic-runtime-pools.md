# ADR 0322: Memory-Pressure Autoscaling For Elastic Runtime Pools

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.144
- Implemented In Platform Version: not yet
- Implemented On: 2026-04-02
- Date: 2026-04-01

## Context

After the runtime tier is split into pools and given explicit memory envelopes,
the next operational gap is response time.

Manual resizing is too slow for the failure mode we already see:

- the platform notices sustained reclaim pressure only after services slow down
  or restart
- one operator or agent must inspect metrics, decide whether to add RAM or
  another runtime node, and then converge that change manually
- by the time that manual action finishes, the original pressure event may
  already have become a wider platform incident

The platform needs an autoscaling control loop, but only one that operates
inside clear bounds and only for pools that are safe to scale.

The platform also wants that control loop to be based on battle-tested OSS with
clear documentation rather than a homegrown autoscaler.

## Decision

We will add a **memory-pressure autoscaling control loop** for elastic runtime
pools.

`Nomad Autoscaler` is the preferred first implementation of that control loop.

### Eligible pools

The first phase allows autoscaling only for:

- `runtime-general`
- `runtime-ai`

`runtime-control` and dedicated state VMs remain fixed-capacity surfaces in the
first phase.

### Required signals

The autoscaler must observe, at minimum:

- available-memory percentage
- memory pressure stall information or equivalent sustained reclaim signal
- swap-in or swap-out activity
- OOM kill or container restart evidence

Optional signals such as queue depth, request latency, or worker backlog may
refine the decision, but they may not replace memory pressure itself.

The preferred source stack is:

- `Prometheus` for memory, pressure, and workload metrics
- `Nomad Autoscaler` policy checks for bounded scale decisions
- `Traefik` for replica-aware routing across scaled pool members
- `Dapr` service invocation ids when pool-local services should address a
  logical application instead of one concrete replica

### Scaling sequence

When a pool crosses its scale-out threshold, the controller must try actions in
this order:

1. scale out horizontally by starting another approved pool member within the
   pool's min and max instance bounds
2. if horizontal scale-out is unavailable, increase the pool's memory within
   the max envelope from ADR 0321
3. when the pool remains below the scale-in threshold for a full cooldown
   window, drain and scale back in, never below the pool minimum

### Default bounds

- `runtime-general`: `min_instances=1`, `max_instances=2`
- `runtime-ai`: `min_instances=1`, `max_instances=2`
- scale out only after sustained pressure above 75% working-set utilisation for
  10 minutes, or immediately after an OOM event
- scale in only after sustained utilisation below 55% for 60 minutes
- never scale if the action would violate the 20 GiB host free-memory floor

### Safety gates

- autoscaling must pause during active deploy or migration waves affecting that
  pool
- autoscaling may act only on services marked eligible by ADR 0323
- every scale action must emit a receipt with the trigger metrics, chosen
  action, and resulting pool state
- Kubernetes-first autoscalers such as `KEDA` are out of scope for the first
  implementation because these runtime pools are not being modeled as a
  Kubernetes estate

## Consequences

**Positive**

- the platform can react to memory pressure before one overloaded runtime takes
  the rest of the estate down with it
- scale-out, resize, and scale-in decisions become governed automation instead
  of ad hoc operator improvisation
- receipts turn scaling behavior into auditable operational history
- future agents can inspect upstream Nomad Autoscaler, Traefik, Dapr, and
  Prometheus docs instead of reading a custom autoscaling codebase first

**Negative / Trade-offs**

- autoscaling adds another control loop that can itself be wrong or noisy if the
  thresholds are poorly tuned
- some pools will still need manual intervention because they are not safe to
  scale automatically

## Boundaries

- This ADR governs autoscaling only for eligible runtime pools.
- It does not authorize autoscaling for stateful anchors, identity services,
  secret authorities, or other fixed-capacity control-plane surfaces.

## Related ADRs

- ADR 0105: Platform capacity model and resource quota enforcement
- ADR 0157: Per-VM concurrency budget and resource reservation
- ADR 0192: Separate capacity classes for standby, recovery, and preview workloads
- ADR 0204: Self-correcting automation loops
- ADR 0232: Nomad for durable batch and long-running internal jobs
