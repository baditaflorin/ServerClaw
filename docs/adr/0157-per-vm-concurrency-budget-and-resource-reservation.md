# ADR 0157: Per-VM Concurrency Budget and Resource Reservation

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.151.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

Parallelism enabled by execution lanes (ADR 0154) and the resource lock registry (ADR 0153) allows multiple agents to execute concurrently across and within VMs. However, concurrency without resource bounds can saturate a VM's CPU, memory, or disk I/O, causing cascading failures across services that have nothing to do with the running operations.

The platform runs on a single Proxmox host (Hetzner CX52: 16 vCPUs, 128 GB RAM). All 7 VMs share this physical resource pool. A scenario where three agents concurrently run Ansible convergence plays — each triggering Docker image pulls, container restarts, and configuration templating — could peak the host's disk I/O, causing every container on every VM to experience elevated response latency.

The existing workflow budget (ADR 0119) enforces per-workflow limits (`max_steps`, `max_touched_hosts`, `max_duration_seconds`) but does not account for **concurrent resource consumption**: 10 concurrent workflows each consuming 10% CPU is equivalent to one workflow consuming 100% CPU and will cause the same contention.

What is needed is a **resource reservation model** where:
1. Each operation declares its expected resource consumption before execution.
2. The platform maintains a real-time **concurrency budget** per VM: a running total of reserved resources.
3. A new operation is admitted only if the budget permits.
4. Reservation is released when the operation completes, freeing budget for the next queued operation.

## Decision

We will implement a **per-VM concurrency budget** with a reservation-based admission control model. Every ExecutionIntent must declare a resource reservation; the admission gate checks the cumulative reservation against the VM's budget before executing.

### Resource reservation specification

Each workflow template in `config/workflow-catalog.yaml` declares an estimated resource footprint:

```yaml
# config/workflow-catalog.yaml — extended with resource_reservation

- workflow_id: converge-netbox
  target_lane: lane:docker-runtime
  resource_reservation:
    cpu_milli: 2000       # 2 vCPUs for the duration of the operation
    memory_mb: 512        # 512 MB additional peak memory
    disk_iops: 100        # Expected peak IOPS during Docker pull/restart
    estimated_duration_seconds: 180
  max_concurrent_instances: 3   # From ADR 0119; independent of budget

- workflow_id: rotate-keycloak-client-secret
  target_lane: lane:docker-runtime
  resource_reservation:
    cpu_milli: 100        # Minimal; just API calls
    memory_mb: 64
    disk_iops: 5
    estimated_duration_seconds: 30

- workflow_id: run-integration-tests
  target_lane: lane:build
  resource_reservation:
    cpu_milli: 4000       # Test suite is CPU-intensive
    memory_mb: 2048
    disk_iops: 500
    estimated_duration_seconds: 600
```

### VM concurrency budget

Each VM has a concurrency budget declared in `config/execution-lanes.yaml`:

```yaml
# config/execution-lanes.yaml — extended with vm_budget

lanes:
  - lane_id: lane:docker-runtime
    vm_id: 120
    vm_budget:
      total_cpu_milli: 6000    # 6 vCPUs available for agent operations
                                # (remainder reserved for services' steady-state needs)
      total_memory_mb: 8192    # 8 GB available for agent operations
      total_disk_iops: 400     # 400 IOPS available; rest reserved for DB and logs
    admission_policy: soft     # 'soft': warn if exceeded, don't hard-block
                                # 'hard': reject new ops if budget would be exceeded

  - lane_id: lane:postgres
    vm_id: 150
    vm_budget:
      total_cpu_milli: 2000
      total_memory_mb: 4096
      total_disk_iops: 200
    admission_policy: hard     # Database operations must be strictly controlled
```

### Budget tracking in NATS KV

The current budget consumption is tracked in NATS JetStream KV (same infrastructure as the lock registry, ADR 0153):

```python
# platform/locking/budget.py

BUDGET_KV_BUCKET = "platform.budgets"

class ConcurrencyBudget:

    def reserve(self, lane_id: str, reservation: ResourceReservation, intent_id: UUID) -> bool:
        """
        Attempt to reserve resources for an intent.
        Returns True if reservation succeeds; False if budget would be exceeded.
        """
        current = self._load_current(lane_id)
        lane_config = load_lane(lane_id)

        projected = ResourceConsumption(
            cpu_milli=current.cpu_milli + reservation.cpu_milli,
            memory_mb=current.memory_mb + reservation.memory_mb,
            disk_iops=current.disk_iops + reservation.disk_iops,
        )

        budget_exceeded = (
            projected.cpu_milli > lane_config.vm_budget.total_cpu_milli or
            projected.memory_mb > lane_config.vm_budget.total_memory_mb or
            projected.disk_iops > lane_config.vm_budget.total_disk_iops
        )

        if budget_exceeded and lane_config.admission_policy == "hard":
            return False  # Caller adds to intent queue (ADR 0155)

        if budget_exceeded and lane_config.admission_policy == "soft":
            # Allow but emit finding
            nats.publish("platform.findings.budget_soft_exceeded", {
                "lane_id": lane_id,
                "intent_id": str(intent_id),
                "projected": projected.__dict__,
                "budget": lane_config.vm_budget.__dict__,
            })

        # Atomic update: add this intent's reservation to current consumption
        self._update_atomic(lane_id, reservation, intent_id, action="reserve")
        return True

    def release(self, lane_id: str, intent_id: UUID):
        """Release the reservation held by this intent."""
        self._update_atomic(lane_id, None, intent_id, action="release")
        # Notify queue scheduler that budget has capacity (ADR 0155)
        nats.publish(f"platform.budget.capacity_available.{lane_id}", {})
```

### Dynamic budget adjustment

For `monitoring-lv3`, the concurrency budget must automatically reduce during a Grafana query spike (when Grafana itself is consuming more than usual). A periodic Windmill workflow `refresh-vm-budgets` queries the Proxmox API for each VM's actual CPU/memory usage and adjusts the available budget dynamically:

```python
# Actual CPU usage from Proxmox API
for vm in proxmox.list_vms():
    actual_cpu = proxmox.get_vm_cpu_usage(vm.vmid)  # 0.0 - 1.0 (fraction of total)
    total_vm_cpu_milli = vm.cpu_cores * 1000
    service_steady_state = catalog.get_steady_state_cpu(vm.vmid)
    available = int(total_vm_cpu_milli * (1 - actual_cpu)) - service_steady_state
    budget.update_available_cpu(lane_id=vm_to_lane(vm.vmid), available_cpu_milli=max(0, available))
```

### Integration with the goal compiler

The resource reservation check is added as a new gate in the goal compiler's pre-execution checklist, between the health composite check (ADR 0128) and Windmill job submission:

```
1. Capability bounds check (ADR 0125)
2. Semantic conflict detection (ADR 0127)
3. Health composite index gate (ADR 0128)
4. → NEW: Concurrency budget reservation (this ADR)
5. Lock registry acquisition (ADR 0153)
6. Submit to Windmill
```

If the budget reservation fails (hard policy) or emits a finding (soft policy), the intent is passed to the intent queue (ADR 0155) with a `queue_if_conflicted=True` flag.

### Observability

The budget state per VM is included in the ops portal (ADR 0093) lane grid view:

```
lane:docker-runtime  [████████░░░░] CPU: 62% reserved | [██████░░░░░░] RAM: 54% | IOPS: 40%
lane:monitoring      [██░░░░░░░░░░] CPU: 18% reserved | [████░░░░░░░░] RAM: 32% | IOPS: 12%
lane:postgres        [████████████] CPU: 100% HARD CAP | (queue depth: 2 waiting)
```

## Consequences

**Positive**

- Agents running in parallel cannot collectively saturate a VM's resources. The concurrency budget is a circuit breaker that prevents a high-parallism scenario from degrading the services the agents are trying to improve.
- Dynamic budget adjustment means the platform self-tunes: when a VM is under load, it admits fewer agent operations; when it is idle, it admits more.
- Soft policy for most VMs allows operations to proceed even if slightly over-budget, with a finding emitted, rather than hard-blocking all progress.

**Negative / Trade-offs**

- Resource reservation values in `workflow-catalog.yaml` are estimates, not measurements. If a workflow actually uses 4x its declared CPU reservation, the budget model is inaccurate. Reservations must be calibrated from historical data (Prometheus metrics for CPU/memory usage during each workflow type).
- The dynamic budget adjustment requires the Windmill workflow runner itself to be on `docker-runtime-lv3`, which is in the budget pool. If the budget manager workflow is CPU-intensive, it consumes budget it is supposed to track.

## Boundaries

- The concurrency budget governs resource admission for agent operations. It does not govern the Proxmox host's overall resource allocation (that is done via Proxmox VM resource settings) or application-level performance tuning.
- Budget reservations are released on operation completion. Reservations do not accumulate across sessions; they are TTL-bounded (max `estimated_duration_seconds * 2` before forced release).

## Related ADRs

- ADR 0058: NATS event bus (JetStream KV for budget state; capacity_available events)
- ADR 0112: Deterministic goal compiler (budget reservation as pre-execution gate)
- ADR 0119: Workflow budget enforcement (per-workflow step/duration limits; complementary)
- ADR 0128: Platform health composite index (health gate before budget gate)
- ADR 0154: VM-scoped execution lanes (lane budget is declared per-lane)
- ADR 0155: Intent queue (intents queued when budget is exhausted)
- ADR 0161: Real-time agent coordination map (budget state visible in live view)
