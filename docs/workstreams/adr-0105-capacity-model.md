# Workstream ADR 0105: Platform Capacity Model and Resource Quota Enforcement

- ADR: [ADR 0105](../adr/0105-platform-capacity-model.md)
- Title: repository-managed host capacity model with reporting, validation, and promotion gate integration
- Status: merged
- Branch: `codex/ws-0105-live-apply`
- Worktree: `../proxmox_florin_server-ws-0105-live-apply`
- Owner: codex
- Depends On: `adr-0010-vm-topology`, `adr-0073-promotion-gate`, `adr-0085-opentofu-vm-lifecycle`, `adr-0097-alerting-routing`, `adr-0098-postgres-ha`
- Conflicts With: none
- Shared Surfaces: `config/`, `scripts/promotion_pipeline.py`, `scripts/lv3_cli.py`, `docs/runbooks/`

## Delivered Scope

- added `config/capacity-model.json` with live-validated allocations for active VMs plus planned `postgres-replica-lv3`
- added `docs/schema/capacity-model.schema.json`
- implemented `scripts/capacity_report.py`
- added `make capacity-report` and `lv3 capacity`
- added the weekly Windmill wrapper `config/windmill/scripts/weekly-capacity-report.py`
- added repository validation coverage in `scripts/validate_repository_data_models.py`
- added baseline capacity enforcement in `scripts/promotion_pipeline.py`
- committed repo-side dashboard and alert artifacts in `config/grafana/dashboards/capacity-overview.json` and `config/alertmanager/rules/platform.yml`
- documented operator procedure in `docs/runbooks/capacity-model.md`
- extended the monitoring converge so Grafana imports the capacity overview dashboard during live apply
- fixed `config/windmill/scripts/weekly-capacity-report.py` so it imports the repo `scripts/` module path from a fresh worktree checkout
- added regression coverage for the monitoring role and weekly Windmill wrapper entry point

## Notes

- live utilisation is collected from InfluxDB on `monitoring-lv3`, not Prometheus
- the backup datastore disk is modeled in committed capacity, but live datastore usage is not yet queried separately
- the dashboard and alert bundle are now verified live on production monitoring and recorded in the canonical mainline receipt/state

## Verification

- `uv run --with pytest python -m pytest tests/test_monitoring_vm_role.py tests/test_capacity_report.py tests/test_lv3_cli.py tests/test_promotion_pipeline.py -q`
- `uv run --with pytest python -m pytest tests/test_weekly_capacity_report_windmill.py -q`
- `make syntax-check-monitoring`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh alert-rules health-probes`
- `make capacity-report NO_LIVE_METRICS=true`
- `make capacity-report`
- `make weekly-capacity-report NO_LIVE_METRICS=true`
- `make weekly-capacity-report`
- `uv run --with pyyaml python scripts/capacity_report.py --model config/capacity-model.json --check-gate --proposed-change 20,8,100`
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 make live-apply-service service=grafana env=production EXTRA_ARGS='-e bypass_promotion=true'`

## Merge Outcome

- repository implementation completed in `0.115.0`
- merged to `main` in `0.177.1`
- platform implementation is now recorded in platform version `0.130.24`
- implementation commit: `851cf901b9bc22515591802fb2fcc5f7a95b6eee`
- the first production replay imported the dashboard and passed its Grafana verification before a later transient SSH reachability failure in the blackbox verification step
- the immediate branch replay completed cleanly with `ok=176 changed=0 unreachable=0 failed=0`
- the current-mainline replay from merge commit `12898d4ef17dc0f8ff3b92523874a61993bed565` completed cleanly with `ok=176 changed=0 unreachable=0 failed=0 skipped=34`
- the dashboard uid `lv3-capacity-overview` is published behind `https://grafana.lv3.org/` and both `make capacity-report` and `make weekly-capacity-report` render with live `ssh+influx` metrics
