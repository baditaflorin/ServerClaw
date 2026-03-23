# ADR 0105: Platform Capacity Model and Resource Quota Enforcement

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-23

## Context

The Proxmox host (`florin`) is a single physical machine with fixed resources: 128 GB RAM, 32 vCPU cores, and a finite NVMe array. The platform currently allocates VM resources by intuition — a VM is given "enough RAM" at the time it is provisioned, and the allocation is never revisited. There is no:

- Declared resource budget per VM (what it is allocated vs what it actually uses)
- Utilisation tracking against budget (is the VM over- or under-allocated?)
- Host-level headroom calculation (what fraction of the host's physical resources are committed?)
- Warning when a new VM or container would push the host into over-commitment territory

The consequence is gradual resource exhaustion that becomes a crisis rather than a managed transition:
- `docker-runtime-lv3` is provisioned with 32 GB RAM but the running containers collectively use 24 GB; if a new service is added without checking, it could push the VM to memory pressure, causing OOM kills
- The Proxmox host has 128 GB RAM; if all VMs are provisioned to their nominal allocations (which is possible when VMs are not actually using their allocation), a snapshot or migration operation may fail due to lack of free RAM for the operation
- Disk space on `local-zfs` is not tracked against a budget; a runaway Docker image build or log volume could fill the pool and crash all VMs

## Decision

We will define a **resource budget model** for the Proxmox host and all VMs, implement weekly utilisation reporting, and add a capacity check to the promotion gate and the VM provisioning workflow.

### Host capacity model

`config/capacity-model.json` declares the physical host's resources and a target utilisation ceiling:

```json
{
  "host": {
    "name": "florin",
    "physical": {
      "ram_gb": 128,
      "vcpu_cores": 32,
      "nvme_tb": 3.6
    },
    "target_utilisation": {
      "ram_percent": 80,
      "vcpu_percent": 75,
      "disk_percent": 75
    },
    "reserved_for_proxmox": {
      "ram_gb": 8,
      "vcpu_cores": 2
    }
  },
  "vms": [
    {
      "vmid": 110,
      "name": "nginx-lv3",
      "allocated": {"ram_gb": 2, "vcpu": 2, "disk_gb": 20},
      "budget": {"ram_gb": 3, "vcpu": 4, "disk_gb": 30}
    },
    {
      "vmid": 120,
      "name": "docker-runtime-lv3",
      "allocated": {"ram_gb": 32, "vcpu": 8, "disk_gb": 200},
      "budget": {"ram_gb": 48, "vcpu": 12, "disk_gb": 300}
    },
    {
      "vmid": 130,
      "name": "docker-build-lv3",
      "allocated": {"ram_gb": 16, "vcpu": 8, "disk_gb": 150},
      "budget": {"ram_gb": 24, "vcpu": 12, "disk_gb": 200}
    },
    {
      "vmid": 140,
      "name": "monitoring-lv3",
      "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 100},
      "budget": {"ram_gb": 12, "vcpu": 8, "disk_gb": 150}
    },
    {
      "vmid": 150,
      "name": "postgres-lv3",
      "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 80},
      "budget": {"ram_gb": 16, "vcpu": 8, "disk_gb": 120}
    },
    {
      "vmid": 151,
      "name": "postgres-replica-lv3",
      "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 80},
      "budget": {"ram_gb": 16, "vcpu": 8, "disk_gb": 120}
    },
    {
      "vmid": 160,
      "name": "backup-lv3",
      "allocated": {"ram_gb": 4, "vcpu": 2, "disk_gb": 2000},
      "budget": {"ram_gb": 8, "vcpu": 4, "disk_gb": 3000}
    }
  ]
}
```

The `allocated` field reflects what the VM is currently configured with in Proxmox. The `budget` field is the maximum the VM may grow to before a capacity review is required.

### Utilisation collection

Telegraf on each VM reports actual resource utilisation to the monitoring stack (already configured in ADR 0032). A new Grafana dashboard **Capacity Overview** aggregates these metrics:

- RAM: allocated vs. average actual usage (7-day mean) vs. budget
- vCPU: allocated vs. CPU usage (7-day p95)
- Disk: allocated vs. used vs. budget

```promql
# RAM utilisation ratio for a VM
(
  avg_over_time(mem_used_bytes{host="docker-runtime-lv3"}[7d])
  /
  (32 * 1024 * 1024 * 1024)  # allocated 32 GB
) * 100
```

### Host headroom calculation

The capacity model script `scripts/capacity_report.py` calculates host-level headroom:

```python
def host_headroom(model: CapacityModel, utilisation: UtilisationData) -> HeadroomReport:
    total_allocated_ram = sum(vm.allocated.ram_gb for vm in model.vms)
    physical_usable_ram = model.host.physical.ram_gb - model.host.reserved_for_proxmox.ram_gb

    return HeadroomReport(
        ram_committed_percent = total_allocated_ram / physical_usable_ram * 100,
        ram_actual_percent = utilisation.total_actual_ram / physical_usable_ram * 100,
        ram_headroom_gb = physical_usable_ram - total_allocated_ram,
        # ... similarly for vCPU and disk
    )
```

### Weekly capacity report

A Windmill workflow `weekly-capacity-report` runs every Monday at 03:00 UTC and posts to Mattermost `#platform-ops`:

```
📊 Capacity Report (2026-03-30)

Host (florin):
  RAM:  78 GB / 120 GB committed (65%) — 7-day actual 52 GB (43%)
  vCPU: 32 / 30 committed (107%!) — 7-day actual p95: 8 cores (27%)
  Disk: 2.2 TB / 3.6 TB used (61%)

⚠️  vCPU over-committed (107%). Actual usage is low, but live migration
    may fail during high-load periods. Consider reducing nginx-lv3 from
    2 vCPU to 1 vCPU if CPU is consistently < 5%.

Underutilised VMs (actual < 30% of budget):
  monitoring-lv3: RAM 3.2 GB / 8 GB budget (40%) — consider reducing budget
```

### Promotion gate integration

Before any deployment that adds a new VM or increases VM resources, the promotion gate (ADR 0073) runs a capacity check:

```python
def check_capacity_gate(proposed_changes: list[VmChange], model: CapacityModel) -> GateResult:
    projected_committed = model.current_committed + sum(c.ram_delta for c in proposed_changes)
    if projected_committed > model.host.physical.ram_gb * model.target_utilisation.ram_percent / 100:
        return GateResult.FAIL(f"Proposed changes would exceed {model.target_utilisation.ram_percent}% RAM commitment target")
    return GateResult.PASS
```

### Alerts

| Condition | Severity | Action |
|---|---|---|
| Host RAM committed > 90% | `warning` | Review VM allocations; reduce over-allocated VMs |
| Host disk usage > 80% | `warning` | Clean up old Docker images and build cache |
| Host disk usage > 90% | `critical` | Immediate action; risk of VM crash |
| VM RAM actual > 90% of allocated | `warning` | Consider increasing VM allocation within budget |

## Consequences

**Positive**
- Resource exhaustion is detected weeks before it becomes a crisis, not during a VM crash
- The budget model separates "what is configured today" from "what we're prepared to grow to" — enabling proactive right-sizing discussions
- The weekly capacity report creates a weekly forcing function for reviewing platform resource health
- The promotion gate prevents accidentally over-provisioning the host when adding new services

**Negative / Trade-offs**
- The capacity model JSON must be kept in sync with actual Proxmox VM configurations; if a VM is resized in the Proxmox UI without updating the JSON, the model will be inaccurate (drift detection in ADR 0091 will catch the config change, but the capacity model update is manual)
- vCPU over-commitment (ratio > 1.0) is normal for Proxmox and does not cause problems unless physical CPU is genuinely saturated; the model must communicate this nuance to avoid false alarms

## Alternatives Considered

- **Proxmox built-in resource pools**: Proxmox supports resource pool quotas; however, they operate at the pool level, not per-VM budget level, and do not integrate with the platform's reporting and alerting model
- **Reactive right-sizing only (resize when things break)**: the current approach; results in emergency late-night resizing operations; avoidable with proactive monitoring
- **Full capacity planning software (Virtusise, VMware vROps equivalent)**: enterprise-grade but over-engineered for a single-node homelab

## Related ADRs

- ADR 0010: Initial Proxmox VM topology (original VM sizing decisions)
- ADR 0085: OpenTofu VM lifecycle (VM resource changes go through OpenTofu)
- ADR 0073: Environment promotion gate (capacity check added here)
- ADR 0097: Alerting routing (capacity alerts route through this model)
- ADR 0098: Postgres HA (adds postgres-replica-lv3 to the capacity model)
