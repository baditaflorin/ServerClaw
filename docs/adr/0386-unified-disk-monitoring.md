# ADR 0386 — Unified Disk Space Monitoring

| Field | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-04-09 |
| **Concerns** | observability, capacity, automation |
| **Supersedes** | — |
| **Depends on** | ADR 0032 (guest observability), ADR 0069 (agent tool registry), ADR 0070 (platform context API), ADR 0105 (capacity model) |

## Context

Disk space monitoring was fragmented:

- Only `nginx-lv3` collected disk metrics via Telegraf `[[inputs.disk]]`.
  All other VMs had Telegraf installed (via `guest_observability`) but
  lacked disk collection.
- Three consumers needed disk data (agent tools, platform-context API,
  Windmill workflows) with no shared query layer.
- Adding or removing a VM would require updating each consumer separately,
  leading to stale monitoring targets.

## Decision

Implement a **three-layer architecture** with a single shared query module:

### Layer 1 — Collection (Telegraf)

Add a shared `telegraf-base-inputs.conf.j2` template to the
`guest_observability` role, deployed to `/etc/telegraf/telegraf.d/lv3-base-inputs.conf`
on every VM.  This provides `[[inputs.disk]]`, `[[inputs.diskio]]`,
`[[inputs.cpu]]`, `[[inputs.mem]]`, `[[inputs.system]]`, `[[inputs.processes]]`,
and `[[inputs.net]]`.

Service-specific Telegraf configs (docker, nginx stub_status, postgres HA)
remain separate overlays in `telegraf.d/`.  The duplicate system inputs
were removed from `nginx_observability`'s template.

### Layer 2 — Shared Query Module

`scripts/disk_metrics.py` provides the single query function
`query_disk_usage()` that:

1. Reads `config/capacity-model.json` for VM enumeration (name, VMID,
   metrics_host, budget, allocated disk).
2. SSH-tunnels to monitoring-lv3 and runs InfluxDB Flux queries for
   `disk.used` and `disk.total` per host per path.
3. Compares actual usage against capacity budgets.
4. Returns a structured `DiskReport` with per-VM, per-mount metrics.

The module reuses the SSH and InfluxDB patterns from `capacity_report.py`.

### Layer 3 — Three Consumers

All three import `disk_metrics.query_disk_usage()`:

| Consumer | File | Interface |
|---|---|---|
| Agent tool | `scripts/agent_tool_registry.py` | `get-disk-usage` handler (category: observe) |
| Platform-context API | `scripts/platform_context_service.py` | `GET /v1/platform/disk-usage?vm=...` |
| Windmill workflow | `config/windmill/scripts/disk-space-monitor.py` | Scheduled every 6h, alerts on threshold |

### Auto-Propagation

When a VM is added to the inventory and `capacity-model.json` (already
required for provisioning):

1. `guest_observability` deploys Telegraf with disk inputs on convergence.
2. All three consumers read `capacity-model.json` dynamically at query
   time — no cached VM lists, zero additional configuration.

When a VM is removed from `capacity-model.json`, it disappears from all
consumers on the next query.

## Consequences

- **DRY**: One collection config, one query module, three consumers.
- **No stale targets**: VM add/remove propagates through existing
  provisioning workflows.
- **Consistent data**: All consumers see the same InfluxDB data through
  the same Flux queries.
- **Existing monitoring enhanced**: Every VM now reports system-level
  metrics (not just nginx-lv3).

## Files

| File | Action |
|---|---|
| `roles/guest_observability/templates/telegraf-base-inputs.conf.j2` | Created |
| `roles/guest_observability/tasks/setup.yml` | Modified |
| `roles/guest_observability/defaults/main.yml` | Modified |
| `roles/nginx_observability/templates/telegraf-nginx.conf.j2` | Modified (removed duplicate system inputs) |
| `scripts/disk_metrics.py` | Created |
| `scripts/agent_tool_registry.py` | Modified (new handler) |
| `config/agent-tool-registry.json` | Modified (new tool entry) |
| `scripts/platform_context_service.py` | Modified (new endpoint) |
| `config/windmill/scripts/disk-space-monitor.py` | Created |
| `config/workflow-catalog.json` | Modified (new workflow entry) |
