# Workstream ADR 0097: Alerting Routing and On-Call Runbook Model

- ADR: [ADR 0097](../adr/0097-alerting-routing-and-oncall-runbook-model.md)
- Title: Alertmanager with severity-based routing to Ntfy and Mattermost, mandatory runbook links on all alert rules, and maintenance window silence integration
- Status: merged
- Branch: `codex/adr-0097-alerting-routing`
- Worktree: `../.worktrees/adr-0097-alerting-routing`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0057-mattermost`, `adr-0061-glitchtip`, `adr-0064-health-probes`, `adr-0080-maintenance-window`, `adr-0091-drift-detection`, `adr-0096-slo-tracking`
- Conflicts With: none
- Shared Surfaces: `config/grafana/provisioning/`, `scripts/maintenance_window_tool.py`, Mattermost webhooks

## Scope

- write Ansible role `alertmanager_runtime` — deploys Alertmanager on `monitoring-lv3` alongside Grafana
- write Ansible role `ntfy_runtime` — deploys Ntfy on `docker-runtime-lv3` as a lightweight push notification service
- write `config/alertmanager/alertmanager.yml` (Ansible-templated) — routing config with ntfy + mattermost receivers
- write `config/alertmanager/rules/platform.yml` — core platform alert rules (Keycloak down, Postgres down, OpenBao sealed, cert expiry)
- update `scripts/maintenance_window_tool.py` — add `create_alertmanager_silence()` call when a window is declared
- add validation gate check: every alert rule in `config/alertmanager/rules/*.yml` must have `runbook_url` and `severity` labels
- write initial runbooks: `docs/runbooks/keycloak-down.md`, `docs/runbooks/postgres-down.md`, `docs/runbooks/openbao-sealed.md`, `docs/runbooks/cert-expired.md`, `docs/runbooks/slo-fast-burn.md`
- add Alertmanager health probe to `config/health-probe-catalog.json`
- add Ntfy health probe to `config/health-probe-catalog.json`

## Non-Goals

- On-call rotation scheduling (single operator platform)
- PagerDuty or OpsGenie integration
- Escalation trees beyond Ntfy → Mattermost

## Expected Repo Surfaces

- `roles/alertmanager_runtime/`
- `roles/ntfy_runtime/`
- `config/alertmanager/alertmanager.yml`
- `config/alertmanager/rules/platform.yml`
- `config/alertmanager/rules/slo_alerts.yml` (from ADR 0096)
- `scripts/maintenance_window_tool.py` (patched)
- `scripts/validate_alert_rules.py` (new: validation gate check)
- `docs/runbooks/keycloak-down.md`
- `docs/runbooks/postgres-down.md`
- `docs/runbooks/openbao-sealed.md`
- `docs/runbooks/cert-expired.md`
- `docs/runbooks/slo-fast-burn.md`
- `config/health-probe-catalog.json` (patched)
- `docs/adr/0097-alerting-routing-and-oncall-runbook-model.md`
- `docs/workstreams/adr-0097-alerting-routing.md`

## Expected Live Surfaces

- Alertmanager running on `monitoring-lv3:9093`
- Ntfy running on `docker-runtime-lv3:2586`
- Declaring a maintenance window via `lv3 maintenance start` creates an Alertmanager silence visible in the Alertmanager UI
- Test alert (fire and resolve a synthetic alert) delivers to Mattermost `#platform-alerts` channel

## Verification

- `curl http://monitoring-lv3:9093/-/healthy` → HTTP 200
- `curl http://docker-runtime-lv3:2586/v1/health` → HTTP 200
- `amtool alert add alertname=TestAlert severity=critical service=test` → verify Mattermost receives notification within 60 seconds
- `amtool alert add alertname=CriticalTest severity=critical service=test` → verify Ntfy delivers push notification (requires Ntfy app installed)
- `lv3 maintenance start --service keycloak --duration 30m` → Alertmanager UI shows silence for keycloak alerts
- Validation gate: add an alert rule without `runbook_url`; verify push is rejected

## Merge Criteria

- Alertmanager deployed and healthy
- Ntfy deployed and healthy
- At least one end-to-end alert notification verified (amtool → Mattermost)
- 5 runbooks written and deployed to docs site
- Maintenance window silence integration tested

## Current Status

- repository implementation merged for `0.97.0`
- live apply still pending; the platform host was not reachable with the documented SSH path during this turn

## Notes For The Next Assistant

- Alertmanager requires Prometheus to be configured with its URL as a remote alertmanager; add `alerting.alertmanagers` to the Prometheus config on `monitoring-lv3`
- Ntfy topics are not password-protected by default; the `platform-alerts` topic must be configured with a subscriber password in `ntfy.conf`; the password is stored in OpenBao at `platform/ntfy/subscriber-password`
- The Mattermost webhook for Alertmanager notifications must be created in Mattermost (`#platform-alerts-critical` and `#platform-alerts` channels); store webhook URLs in OpenBao at `platform/mattermost/webhooks/`
- `validate_alert_rules.py` should be added to `config/validation-gate.json` as a new gate check with severity `error`
