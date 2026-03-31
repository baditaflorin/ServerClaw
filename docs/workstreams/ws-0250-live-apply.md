# Workstream ws-0250-live-apply: Live Apply ADR 0250 From Latest `origin/main`

- ADR: [ADR 0250](../adr/0250-log-ingestion-and-queryability-canaries-via-loki-canary.md)
- Title: production live apply for Loki Canary-backed log ingestion and queryability assurance on the shared monitoring stack
- Status: live_applied
- Implemented In Repo Version: 0.177.57
- Live Applied In Platform Version: 0.130.44
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0250-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0250-live-apply`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0052-loki-logs`,
  `adr-0097-alerting-routing`, `adr-0244-runtime-assurance-matrix`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/monitoring_vm/`,
  `collections/ansible_collections/lv3/platform/roles/alertmanager_runtime/tasks/verify.yml`,
  `config/alertmanager/rules/platform.yml`,
  `config/grafana/dashboards/log-canary-overview.json`,
  `docs/adr/0250-log-ingestion-and-queryability-canaries-via-loki-canary.md`,
  `docs/runbooks/log-queryability-canary.md`,
  `docs/runbooks/monitoring-stack.md`,
  `docs/workstreams/ws-0250-live-apply.md`,
  `receipts/live-applies/2026-03-28-adr-0250-log-queryability-canary-live-apply.json`,
  `tests/test_alertmanager_runtime_role.py`,
  `tests/test_monitoring_vm_role.py`,
  `workstreams.yaml`

## Scope

- add a repo-managed Loki Canary runtime to `monitoring-lv3`
- scrape Loki Canary metrics in Prometheus, render an operator dashboard in
  Grafana, and alert on missing or non-queryable canary entries
- document the operational procedure and record verified live evidence from the
  latest `origin/main`
- repair the live-replay issues uncovered during rollout: canary rule
  verification ordering, the actual Loki selector, and ADR 0165 metadata-gate
  compliance on the touched Ansible files

## Verification

- `uv run --with pytest python -m pytest tests/test_monitoring_vm_role.py tests/test_alertmanager_runtime_role.py tests/test_validate_alert_rules.py -q`
- `make syntax-check-monitoring`
- `UV_PROJECT_ENVIRONMENT=/tmp/proxmox-ws0250-validate ./scripts/validate_repo.sh alert-rules agent-standards yaml json role-argument-specs workstream-surfaces`
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=grafana env=production EXTRA_ARGS='-e bypass_promotion=true'`
- host verification over the Proxmox jump path to `ops@10.10.10.40`:
  `systemctl is-active loki-canary lv3-prometheus grafana-server prometheus-alertmanager`,
  `curl http://127.0.0.1:3500/metrics`, `curl http://127.0.0.1:9090/api/v1/query`,
  `curl http://127.0.0.1:9090/api/v1/rules`, `curl http://127.0.0.1:3100/loki/api/v1/query_range`,
  `curl -u admin:... http://127.0.0.1:3000/api/dashboards/uid/lv3-log-canary-overview`,
  and `curl -I https://grafana.lv3.org/d/lv3-log-canary-overview/lv3-log-canary-overview`

## Live Apply Outcome

- the focused integrated validation slice passed on the final mainline state:
  `uv run --with pytest python -m pytest tests/test_monitoring_vm_role.py tests/test_alertmanager_runtime_role.py tests/test_validate_alert_rules.py -q` returned `13 passed in 0.91s`,
  `make syntax-check-monitoring` passed, and
  `UV_PROJECT_ENVIRONMENT=/tmp/proxmox-ws0250-validate ./scripts/validate_repo.sh alert-rules agent-standards yaml json role-argument-specs workstream-surfaces` completed successfully
- the guarded replay from `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0250-main-integration-v2`
  completed successfully with recap `monitoring-lv3 : ok=191 changed=8 failed=0`
- the replay used the documented ADR 0191 narrow in-place mutation exception for
  reversible monitoring-stack changes on `monitoring-lv3`
- `loki-canary`, `lv3-prometheus`, `grafana-server`, and the managed
  `prometheus-alertmanager.service` were all active after the replay, with
  Alertmanager `/-/healthy` and `/-/ready` both returning `OK`
- direct canary metrics verification returned `loki_canary_entries_total 18`,
  `loki_canary_missing_entries_total 0`, and
  `loki_canary_spot_check_missing_entries_total 0`
- Prometheus returned `up{job="loki-canary"} == 1` and the rule group
  `lv3-log-canary` was loaded
- direct Loki queries returned the canary stream under the verified selector
  `{name="loki-canary",stream="stdout"}` and the stream labels
  `name=loki-canary`, `stream=stdout`, `service_name=loki-canary`
- Grafana returned dashboard title `LV3 Log Canary` for UID
  `lv3-log-canary-overview`, while the public dashboard URL redirected
  unauthenticated users to `/login`

## Mainline Integration

- release `0.177.57` now carries ADR 0250 on `main`
- platform version `0.130.44` records the verified live Loki Canary assurance
  state
- the final mainline integration step updated `VERSION`, `changelog.md`,
  `RELEASE.md`, `docs/release-notes/0.177.57.md`,
  `docs/release-notes/README.md`, `README.md`, `versions/stack.yaml`,
  `build/platform-manifest.json`, the ADR metadata, the workstream metadata,
  and the live-apply receipt

## Live Evidence

- receipt: `receipts/live-applies/2026-03-28-adr-0250-log-queryability-canary-live-apply.json`
- the live replay initially exposed two branch-local defects that were fixed
  before the successful apply:
  rule verification had to move from `monitoring_vm` into
  `alertmanager_runtime`, and the effective Loki selector had to switch from the
  attempted custom labels to `{name="loki-canary",stream="stdout"}`
- the touched Ansible task, handler, and argument-spec files gained ADR 0165
  metadata headers so `scripts/validate_repo.sh agent-standards` accepts the
  workstream during the final integrated validation run

## Merge-To-Main Notes

- remaining for merge to `main`: none
