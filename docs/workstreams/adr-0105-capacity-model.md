# Workstream ADR 0105: Platform Capacity Model and Resource Quota Enforcement

- ADR: [ADR 0105](../adr/0105-platform-capacity-model.md)
- Title: capacity-model.json tracking physical host and per-VM resource budgets with weekly Windmill report, Grafana dashboard, and promotion gate check
- Status: ready
- Branch: `codex/adr-0105-capacity-model`
- Worktree: `../proxmox_florin_server-capacity-model`
- Owner: codex
- Depends On: `adr-0010-vm-topology`, `adr-0073-promotion-gate`, `adr-0085-opentofu-vm-lifecycle`, `adr-0097-alerting-routing`, `adr-0098-postgres-ha`
- Conflicts With: none
- Shared Surfaces: `config/`, `scripts/promotion_pipeline.py`, `config/grafana/dashboards/`

## Scope

- write `config/capacity-model.json` — host physical resources, per-VM allocations, budgets, and target utilisation ceilings
- write `scripts/capacity_report.py` — reads the model and queries Prometheus for actual utilisation; produces headroom report
- write Windmill workflow `weekly-capacity-report` — scheduled Monday 03:00 UTC; calls `capacity_report.py` and posts to Mattermost
- write Grafana dashboard `config/grafana/dashboards/capacity-overview.json` — allocated vs. actual vs. budget per VM
- add Grafana alerts: host RAM committed > 90%, host disk > 80%, host disk > 90%, VM RAM actual > 90% of allocated
- add `config/capacity-model.json` alerts to `config/alertmanager/rules/platform.yml`
- update `scripts/promotion_pipeline.py` — add `check_capacity_gate()` that blocks promotion if new VMs would exceed target utilisation
- add `lv3 capacity` command to platform CLI — runs capacity_report.py and prints output
- add `config/capacity-model.json` to the JSON schema validation gate
- update `config/capacity-model.json` to include `postgres-replica-lv3` (VMID 151 from ADR 0098)

## Non-Goals

- Automatic VM right-sizing (resize is always an operator-initiated action)
- Container-level resource tracking within VMs (VM-level granularity only)
- CPU/RAM reservation enforcement in Proxmox (informational model only; not hard quotas)

## Expected Repo Surfaces

- `config/capacity-model.json`
- `scripts/capacity_report.py`
- `config/grafana/dashboards/capacity-overview.json`
- `config/alertmanager/rules/platform.yml` (patched: capacity alerts)
- `scripts/promotion_pipeline.py` (patched: capacity gate)
- Makefile (patched: `make capacity-report` target)
- `docs/adr/0105-platform-capacity-model.md`
- `docs/workstreams/adr-0105-capacity-model.md`

## Expected Live Surfaces

- Grafana Capacity Overview dashboard is accessible and shows current utilisation vs. budget for all VMs
- `lv3 capacity` prints a capacity summary with current utilisation and headroom
- Weekly capacity report workflow has at least one successful run in Windmill
- Mattermost `#platform-ops` received the capacity report

## Verification

- `lv3 capacity` runs without error and shows > 10% headroom on all resources
- Grafana Capacity Overview dashboard loads without errors and shows non-zero RAM usage for all VMs
- Capacity gate check: temporarily reduce `target_utilisation.ram_percent` to 10% in the model; run `lv3 promote --env production`; verify it fails with capacity message; restore the value

## Merge Criteria

- `config/capacity-model.json` reflects actual current VM allocations (verify against `qm config` for each VMID)
- Grafana Capacity Overview dashboard deployed and showing data
- Weekly capacity report workflow scheduled and tested
- Capacity gate added to promotion pipeline

## Notes For The Next Assistant

- Actual RAM and CPU usage data comes from Telegraf's `mem` and `cpu` inputs, already collected (ADR 0032); verify the metric names in Prometheus before writing the PromQL queries (`mem_used_bytes`, `cpu_usage_active` etc.; names vary by Telegraf version)
- The `allocated` values in `config/capacity-model.json` must be read from actual Proxmox VM configs via `qm config <vmid>` — do not guess; verify each VM's actual configured RAM and vCPU before writing the JSON
- Include the ephemeral VM pool (from ADR 0106) in the capacity model as a reserved block; this ensures that the capacity gate accounts for peak ephemeral VM usage
- Disk utilisation: query `disk_used_percent{path="/"}` for each VM; for `backup-lv3`, query the PBS datastore utilisation from the PBS API
