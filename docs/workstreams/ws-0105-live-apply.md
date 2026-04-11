# Workstream ws-0105-live-apply: Live Apply ADR 0105 From Latest `origin/main`

- ADR: [ADR 0105](../adr/0105-platform-capacity-model.md)
- Title: production live apply for the capacity dashboard, capacity report entry points, and monitoring verification from the latest `origin/main`
- Status: merged
- Branch: `codex/ws-0105-live-apply`
- Worktree: `../proxmox-host_server-ws-0105-live-apply`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0097-alerting-routing`, `adr-0105-capacity-model`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/monitoring_vm/`, `config/grafana/dashboards/capacity-overview.json`, `config/alertmanager/rules/platform.yml`, `config/windmill/scripts/weekly-capacity-report.py`, `docs/runbooks/capacity-model.md`, `receipts/live-applies/`

## Scope

- extend the monitoring role so the Grafana converge copies, imports, and verifies `lv3-capacity-overview`
- keep the repo-managed alert-rule bundle active on the same monitoring surface
- fix the weekly Windmill wrapper so fresh worktrees can import `scripts/capacity_report.py`
- validate the repo automation paths and perform the production live apply from the latest `origin/main`

## Verification

- `uv run --with pytest python -m pytest tests/test_monitoring_vm_role.py tests/test_capacity_report.py tests/test_lv3_cli.py tests/test_promotion_pipeline.py -q`
- `uv run --with pytest python -m pytest tests/test_weekly_capacity_report_windmill.py -q`
- `uv run --with pytest python -m pytest tests/test_run_namespace.py tests/test_ansible_execution_scopes.py tests/test_remote_exec.py -q`
- `make syntax-check-monitoring`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh alert-rules health-probes`
- `make capacity-report NO_LIVE_METRICS=true`
- `make capacity-report`
- `make weekly-capacity-report NO_LIVE_METRICS=true`
- `make weekly-capacity-report`
- `uv run --with pyyaml python scripts/capacity_report.py --model config/capacity-model.json --check-gate --proposed-change 20,8,100`
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 make live-apply-service service=grafana env=production EXTRA_ARGS='-e bypass_promotion=true'`
- `curl -Ik --resolve grafana.example.com:443:203.0.113.1 https://grafana.example.com/d/lv3-capacity-overview/lv3-capacity-overview`

## Outcome

- implementation commit `2907637daca87ee2bb739c0dd821eee0834aa319` adds the capacity dashboard converge plus the fresh-worktree weekly wrapper fix
- the first production replay imported and verified the dashboard, then later hit a transient SSH reachability failure in a downstream verification task
- the immediate replay completed cleanly with `ok=176 changed=0 unreachable=0 failed=0 skipped=34`
- the current-mainline replay from source commit `2907637daca87ee2bb739c0dd821eee0834aa319` completed cleanly with `ok=176 changed=0 unreachable=0 failed=0 skipped=34`
- the current-mainline replay also proved the official live-apply entrypoint from a separate worktree after shortening per-run Ansible control-socket directories under `/tmp`
- merged to `main` in repo version `0.177.5`, with the live platform version advanced to `0.130.26`
- the public dashboard path redirects to Grafana login, confirming the live route for uid `lv3-capacity-overview`
- `make capacity-report` and `make weekly-capacity-report` both render successfully with live `metrics_source: ssh+influx`
