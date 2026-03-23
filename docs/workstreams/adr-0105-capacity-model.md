# Workstream ADR 0105: Platform Capacity Model and Resource Quota Enforcement

- ADR: [ADR 0105](../adr/0105-platform-capacity-model.md)
- Title: repository-managed host capacity model with reporting, validation, and promotion gate integration
- Status: merged
- Branch: `codex/adr-0105-capacity-model`
- Worktree: `.worktrees/adr-0105`
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

## Notes

- live utilisation is collected from InfluxDB on `monitoring-lv3`, not Prometheus
- the backup datastore disk is modeled in committed capacity, but live datastore usage is not yet queried separately
- dashboard and alert artifacts are committed in the repo but not yet marked live-applied

## Verification

- `python3 -m pytest tests/test_capacity_report.py tests/test_lv3_cli.py tests/test_promotion_pipeline.py`
- `python3 scripts/validate_repository_data_models.py --validate`
- `python3 scripts/capacity_report.py --model config/capacity-model.json --no-live-metrics`
- `python3 scripts/capacity_report.py --model config/capacity-model.json --check-gate --proposed-change 20,8,100`

## Merge Outcome

- repository implementation complete in `0.115.0`
- live platform application deferred
