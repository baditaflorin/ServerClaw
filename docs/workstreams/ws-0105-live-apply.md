# Workstream ws-0105-live-apply: Live Apply ADR 0105 From Latest `origin/main`

- ADR: [ADR 0105](../adr/0105-platform-capacity-model.md)
- Title: production live apply for the capacity dashboard, capacity report entry points, and monitoring verification from the latest `origin/main`
- Status: merged
- Branch: `codex/ws-0105-live-apply`
- Worktree: `../proxmox_florin_server-ws-0105-live-apply`
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
- `make syntax-check-monitoring`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh alert-rules health-probes`
- `make capacity-report NO_LIVE_METRICS=true`
- `make capacity-report`
- `make weekly-capacity-report NO_LIVE_METRICS=true`
- `make weekly-capacity-report`
- `uv run --with pyyaml python scripts/capacity_report.py --model config/capacity-model.json --check-gate --proposed-change 20,8,100`
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 make live-apply-service service=grafana env=production EXTRA_ARGS='-e bypass_promotion=true'`
- `curl -Ik --resolve grafana.lv3.org:443:65.108.75.123 https://grafana.lv3.org/d/lv3-capacity-overview/lv3-capacity-overview`

## Outcome

- implementation commit `851cf901b9bc22515591802fb2fcc5f7a95b6eee` adds the capacity dashboard converge plus the fresh-worktree weekly wrapper fix
- the first production replay imported and verified the dashboard, then later hit a transient SSH reachability failure in a downstream verification task
- the immediate replay completed cleanly with `ok=176 changed=0 unreachable=0 failed=0`
- the current-mainline replay from merge commit `12898d4ef17dc0f8ff3b92523874a61993bed565` completed cleanly with `ok=176 changed=0 unreachable=0 failed=0 skipped=34`
- merged to `main` in repo version `0.177.1`, with the live platform version advanced to `0.130.24`
- the public dashboard path redirects to Grafana login, confirming the live route for uid `lv3-capacity-overview`
- `make capacity-report` and `make weekly-capacity-report` both render successfully with live `metrics_source: ssh+influx`
