# Capacity Model

This runbook covers the repository-managed capacity model introduced by ADR 0105.

## Purpose

- keep one declared view of physical host capacity, current VM allocations, planned growth, and reserved ephemeral headroom
- make R2 and higher standby claims machine-checkable before a production live apply
- report current commitments alongside live utilisation from the monitoring VM
- provide a reusable gate for promotions and future provisioning workflows

## Repository Surfaces

- `config/capacity-model.json`
- `config/service-capability-catalog.json`
- `docs/schema/capacity-model.schema.json`
- `docs/schema/service-capability-catalog.schema.json`
- `scripts/capacity_report.py`
- `scripts/standby_capacity.py`
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
uv run --with pyyaml python scripts/capacity_report.py \
  --check-gate \
  --proposed-change 20,8,100
```

Validate all R2/R3 standby declarations and their placement backing:

```bash
uv run --with pyyaml python scripts/standby_capacity.py --validate
```

Inspect one service before a manual production live apply:

```bash
uv run --with pyyaml python scripts/standby_capacity.py --service postgres
```

Render the weekly markdown report through the repo entry point:

```bash
make weekly-capacity-report
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
3. if the service claims `R2` or higher, update its `redundancy.standby` declaration in `config/service-capability-catalog.json`
4. run `uv run --with pyyaml python scripts/standby_capacity.py --validate`
5. run `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
6. run `uv run --with pytest python -m pytest tests/test_capacity_report.py tests/test_lv3_cli.py tests/test_promotion_pipeline.py tests/test_standby_capacity.py tests/test_validate_service_catalog.py tests/test_weekly_capacity_report_windmill.py`
7. if monitoring surfaces changed, run `make syntax-check-monitoring` and `./scripts/validate_repo.sh alert-rules health-probes`
8. if the integrated mainline truth changes, update ADR/workstream status metadata and release notes on merge

## Live Apply

For the ADR 0105 monitoring rollout from a parallel worktree, apply the Grafana service bundle directly:

```bash
BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
make live-apply-service service=grafana env=production EXTRA_ARGS='-e bypass_promotion=true'
```

Verify the dashboard and reports after converge:

```bash
make capacity-report
make weekly-capacity-report
curl -Ik --resolve grafana.lv3.org:443:65.108.75.123 \
  https://grafana.lv3.org/d/lv3-capacity-overview/lv3-capacity-overview
```

For a guest-local Grafana check through the Proxmox jump path, query `http://127.0.0.1:3000/api/dashboards/uid/lv3-capacity-overview` on `monitoring-lv3`.

## Notes

- `postgres-replica-lv3` is modeled as planned capacity until the VM exists live
- the `ephemeral-pool` reservation protects ADR 0106 fixture headroom even when no ephemeral VMs are active
- a standby can be backed either by a dedicated guest already declared in the capacity model or by an explicit `standby` reservation entry when the standby consumes host headroom without its own guest allocation
- `make live-apply-service service=<id> env=production` now runs the standby-capacity guard before Ansible
- the committed dashboard and alert rules are repository artifacts only until they are applied from `main`
- fresh worktrees do not carry untracked `.local/` controller secrets, so live applies from a parallel worktree should pass an absolute `BOOTSTRAP_KEY` or equivalent controller-local path explicitly
- `config/windmill/scripts/weekly-capacity-report.py` prepends the repository `scripts/` directory to `sys.path` so the wrapper works from a clean checkout or worktree
