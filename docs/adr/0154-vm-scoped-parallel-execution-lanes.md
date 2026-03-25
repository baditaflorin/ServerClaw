# ADR 0154: VM-Scoped Parallel Execution Lanes

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform runs on a single Proxmox host with seven VMs. Each VM is operationally independent: a change on `monitoring-lv3` (VM 140) does not directly affect services on `docker-runtime-lv3` (VM 120). Yet the current execution model is effectively serialised: the goal compiler (ADR 0112) and conflict detector (ADR 0127) treat all active intents as potentially conflicting and block a new intent if any execution is in progress on the same service, regardless of which VM it targets.

In a multi-agent scenario where three concurrent sessions are working on different goals:
- Agent A: Rotate Grafana service account token on `monitoring-lv3`
- Agent B: Update NetBox IPAM prefixes on `docker-runtime-lv3`
- Agent C: Rebuild the docs portal on `docker-build-lv3`

None of these operations share any resources at the VM level. They could all execute simultaneously in 3 minutes instead of sequentially in 9 minutes. But today they serialise.

The Proxmox VM is the natural unit of isolation for infrastructure operations:
- Ansible connects to each VM via SSH independently.
- Docker Compose restarts on one VM do not affect containers on another.
- A failed deployment to one VM does not cascade to others (absent an application-level dependency).
- The Proxmox hypervisor schedules VM CPU/memory independently.

Formalising this into explicit **execution lanes** — one lane per VM — makes the parallelism model explicit, auditable, and toolable: agents request a lane, operations in different lanes run concurrently, operations in the same lane queue.

## Decision

We will define **VM-scoped parallel execution lanes** as the primary unit of concurrency in the platform. Each VM has exactly one execution lane. Operations within a lane are serialised; operations in different lanes run in parallel.

### Lane definitions

```yaml
# config/execution-lanes.yaml

lanes:
  - lane_id: lane:nginx
    vm_id: 110
    hostname: nginx-lv3
    services: [nginx]
    max_concurrent_ops: 1        # Only 1 op at a time on this VM
    serialisation: strict        # No pipeline; each op completes before next starts

  - lane_id: lane:docker-runtime
    vm_id: 120
    hostname: docker-runtime-lv3
    services:
      - netbox
      - keycloak
      - windmill
      - mattermost
      - open-webui
      - platform-api
      - gitea
      - ollama
      - vaultwarden
      - searxng
      - n8n
      - langfuse
      - dozzle-hub
    max_concurrent_ops: 3        # Up to 3 concurrent ops on this VM
    # Services within this lane can run concurrently because Docker Compose
    # restarts are container-scoped; they don't affect each other.
    serialisation: resource_lock  # Parallelism governed by lock registry (ADR 0153)

  - lane_id: lane:build
    vm_id: 130
    hostname: docker-build-lv3
    services: [build-worker, gitea-runner]
    max_concurrent_ops: 2
    serialisation: resource_lock

  - lane_id: lane:monitoring
    vm_id: 140
    hostname: monitoring-lv3
    services: [grafana, prometheus, alertmanager, loki, tempo]
    max_concurrent_ops: 2
    serialisation: resource_lock

  - lane_id: lane:postgres
    vm_id: 150
    hostname: postgres-lv3
    services: [postgresql]
    max_concurrent_ops: 1        # DB schema migrations must be strictly serialised
    serialisation: strict

  - lane_id: lane:postgres-replica
    vm_id: 151
    hostname: postgres-replica-lv3
    services: [postgresql-standby]
    max_concurrent_ops: 1
    serialisation: strict

  - lane_id: lane:backup
    vm_id: 160
    hostname: backup-lv3
    services: [proxmox-backup-server]
    max_concurrent_ops: 1
    serialisation: strict

  # Cross-VM operations that span multiple lanes
  - lane_id: lane:platform
    vm_id: null                  # Not VM-specific; covers platform-wide operations
    services: [keycloak-realm-config, dns-zone, openbao-policies]
    max_concurrent_ops: 1
    serialisation: strict
    # This lane is acquired when an operation affects config that is read by
    # services on multiple VMs (e.g., a Keycloak realm change affects all OIDC clients)
```

### Lane assignment in the goal compiler

The goal compiler (ADR 0112) resolves which lanes an ExecutionIntent requires before calling the lock registry (ADR 0153):

```python
# platform/locking/lanes.py

def resolve_lanes(intent: ExecutionIntent) -> list[str]:
    """Determine which execution lanes an intent requires."""
    catalog_entry = capability_catalog.get(intent.service_id)
    primary_lane = f"lane:{catalog_entry.vm_hostname.split('-')[0]}"

    lanes = [primary_lane]

    # Cross-VM service dependencies
    for dep in catalog_entry.dependencies:
        dep_entry = capability_catalog.get(dep)
        dep_lane = f"lane:{dep_entry.vm_hostname.split('-')[0]}"
        if dep_lane != primary_lane:
            lanes.append(dep_lane)
            # Acquiring a dependency's lane is shared (read), not exclusive.
            # The primary lane is exclusive (write).

    return lanes

# Goal compiler integration
intent.required_lanes = resolve_lanes(intent)
for lane in intent.required_lanes:
    registry.acquire(f"vm:{lane_vmid(lane)}", lock_type=LockType.EXCLUSIVE if lane == primary_lane else LockType.SHARED)
```

### Lane scheduler

The lane scheduler is a Windmill workflow `lane-scheduler` that runs as a persistent service (Windmill recurring trigger, every 2 seconds). It monitors the lane state and dequeues the next intent from the intent queue (ADR 0155) for each lane that has available capacity:

```python
# config/windmill/scripts/lane-scheduler.py

def tick():
    for lane in load_lane_definitions():
        current_ops = count_executing_ops_in_lane(lane.lane_id)
        available = lane.max_concurrent_ops - current_ops
        if available <= 0:
            continue
        # Dequeue the next intent for this lane (ADR 0155)
        next_intents = intent_queue.peek(lane_id=lane.lane_id, count=available)
        for intent in next_intents:
            if can_acquire_locks(intent):
                intent_queue.dequeue(intent.intent_id)
                submit_to_windmill(intent)
```

### Parallelism visualisation

The ops portal (ADR 0093) and Homepage dashboard (ADR 0152) display a live lane grid:

```
╔═══════════════════════════════════════════════════════════════════╗
║ EXECUTION LANES                           2026-03-24 14:32:01    ║
╠══════════════════╦═════════════════════════╦═════════════════════╣
║ lane:docker-rt   ║ ████ rotate-keycloak    ║ 1/3 slots           ║
║ lane:monitoring  ║ ████ update-grafana-ds  ║ 1/2 slots           ║
║ lane:build       ║ [idle]                  ║ 0/2 slots           ║
║ lane:nginx       ║ [idle]                  ║ 0/1 slots           ║
║ lane:postgres    ║ QUEUED: netbox-migrate  ║ 0/1 slots (blocked) ║
╚══════════════════╩═════════════════════════╩═════════════════════╝

3 ops running in parallel across 2 lanes.
Estimated completion: rotate-keycloak 2m | update-grafana-ds 4m
```

### Cross-lane operations (service dependency graph)

Some operations require coordination across lanes. For example, deploying a new version of Keycloak (`lane:docker-runtime`) requires verifying that `ops.lv3.org` (nginx, `lane:nginx`) will still reach it. Cross-lane operations:

1. Acquire the primary lane as `exclusive`.
2. Acquire each dependency's lane as `shared` (intent lock only — reading state, not mutating).
3. If any required lane cannot be acquired within the wait budget (ADR 0157), the intent is queued (ADR 0155) rather than rejected.

## Consequences

**Positive**

- The throughput for multi-agent parallel workloads increases proportionally to the number of independent lanes. With 7 VMs, up to 7 completely independent operations can run simultaneously, plus 5+ concurrent container-level operations within `lane:docker-runtime`.
- The lane model is simple to reason about: "will these two operations conflict?" reduces to "do they require the same lane exclusively?"
- The lane grid in the ops portal gives operators and agents instant situational awareness: which VMs are busy, which are idle, what is queued.

**Negative / Trade-offs**

- `lane:docker-runtime` hosts the most services (15+). It is the most likely to become the bottleneck. The `max_concurrent_ops: 3` limit is a tuning parameter that must be calibrated against the actual CPU and memory headroom on that VM.
- Cross-lane dependency detection requires the service capability catalog to declare inter-VM dependencies accurately. Missing or wrong dependency declarations cause either missed blocking (unsafe) or excessive blocking (slow).

## Related ADRs

- ADR 0075: Service capability catalog (VM placement and dependencies used for lane resolution)
- ADR 0112: Deterministic goal compiler (lane assignment integrated here)
- ADR 0115: Event-sourced mutation ledger (lane IDs recorded in intent events)
- ADR 0127: Intent conflict detection (semantic layer; lane conflicts are structural)
- ADR 0153: Distributed resource lock registry (lock acquisition per lane)
- ADR 0155: Intent queue with release-triggered scheduling (lane scheduler dequeues from this)
- ADR 0157: Per-VM concurrency budget (capacity limits per lane)
- ADR 0161: Real-time agent coordination map (displays live lane occupancy)
