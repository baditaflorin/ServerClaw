# Capacity Model

This runbook covers the repository-managed capacity model introduced by ADR 0105.

## Purpose

- keep one declared view of physical host capacity, current VM allocations, planned growth, and reserved ephemeral headroom
- report current commitments alongside live utilisation from the monitoring VM
- provide a reusable gate for promotions and future provisioning workflows

## Repository Surfaces

- `config/capacity-model.json`
- `docs/schema/capacity-model.schema.json`
- `scripts/capacity_report.py`
- `config/windmill/scripts/weekly-capacity-report.py`
- `config/grafana/dashboards/capacity-overview.json`
- `config/alertmanager/rules/platform.yml`

## Commands

Render the default text report:

```bash
make capacity-report
```

Render without live metrics:

```bash
make capacity-report NO_LIVE_METRICS=true
```

Render through the operator CLI:

```bash
lv3 capacity --no-live-metrics
lv3 capacity --format json
```

Evaluate a proposed resource change against the active commitment target:

```bash
python3 scripts/capacity_report.py \
  --check-gate \
  --proposed-change 20,8,100
```

## Live Metrics Path

- the report reads the committed model from `config/capacity-model.json`
- when live metrics are enabled it SSHes to `monitoring-lv3` through the Proxmox jump host
- on `monitoring-lv3` it runs `influx query` against the local InfluxDB API
- memory uses the 7-day mean of `mem.used`
- CPU uses the 7-day p95 of `cpu.usage_active` for `cpu-total`
- disk currently uses the latest `disk.used` sample for `/`

If the monitoring path is unavailable, the report still renders using the committed model and marks live metrics as unavailable.

## Update Procedure

1. verify live VM allocations with `qm config <vmid>` on the Proxmox host
2. update `config/capacity-model.json`
3. run `python3 scripts/validate_repository_data_models.py --validate`
4. run `python3 -m pytest tests/test_capacity_report.py tests/test_lv3_cli.py tests/test_promotion_pipeline.py`
5. if the integrated mainline truth changes, update ADR/workstream status metadata and release notes on merge

## Notes

- `postgres-replica-lv3` is modeled as planned capacity until the VM exists live
- the `ephemeral-pool` reservation protects ADR 0106 fixture headroom even when no ephemeral VMs are active
- the committed dashboard and alert rules are repository artifacts only until they are applied from `main`
