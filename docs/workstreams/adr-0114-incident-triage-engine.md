# Workstream ADR 0114: Rule-Based Incident Triage Engine

- ADR: [ADR 0114](../adr/0114-rule-based-incident-triage-engine.md)
- Title: CPU-only triage engine triggered on every firing alert — assembles signals from world state, evaluates ranked rules, posts hypotheses and cheapest first action to Mattermost before any operator acts
- Status: merged
- Branch: `codex/adr-0114-incident-triage`
- Worktree: `.worktrees/adr-0114`
- Owner: codex
- Depends On: `adr-0052-loki-logs`, `adr-0057-mattermost-chatops`, `adr-0058-nats-event-bus`, `adr-0061-glitchtip`, `adr-0064-health-probe-contracts`, `adr-0097-alerting-routing`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`, `adr-0117-dependency-graph-runtime`
- Conflicts With: none
- Shared Surfaces: `scripts/incident_triage.py`, `scripts/triage_calibration.py`, `config/triage-rules.yaml`, `config/windmill/scripts/`, mutation-audit sink

## Scope

- create `scripts/incident_triage.py` — context assembly, signal extraction, rule evaluation, hypothesis ranking, and report emission
- create `scripts/triage_calibration.py` — weekly precision and recall summariser over resolved incident cases
- create `config/triage-rules.yaml` — initial rule set with at minimum: `recent-deployment-regression`, `upstream-db-saturation`, `tls-cert-expiry`, `resource-exhaustion`, `dependency-failure`, `configuration-drift`
- create `config/triage-auto-check-allowlist.yaml` — explicit safe auto-check types
- create `config/windmill/scripts/run-triage.py` — Windmill workflow that receives an alert payload, calls the triage engine, and emits output
- create `config/windmill/scripts/calibrate-triage-rules.py` — weekly workflow that computes per-rule precision/recall and posts a summary
- update `config/workflow-catalog.json` and `Makefile` — repo-managed entrypoints for triage and calibration
- write `tests/test_incident_triage.py` and `tests/test_triage_windmill.py` — unit tests for rule evaluation, emission, and Windmill wrappers
- write `docs/runbooks/incident-triage-engine.md` — operator runbook for payload contract, outputs, safety rules, and verification

## Non-Goals

- Autonomous remediation (unless `auto_check: true` for a specific discriminating check) — triage proposes, humans decide
- Writing the case library integration (ADR 0118) — that workstream adds the `similar_cases` block to triage reports once the case library exists
- Writing the alert routing rules (ADR 0097) — this workstream consumes the alert events that ADR 0097 fires

## Expected Repo Surfaces

- `scripts/incident_triage.py`
- `scripts/triage_calibration.py`
- `config/triage-rules.yaml`
- `config/triage-auto-check-allowlist.yaml`
- `config/windmill/scripts/run-triage.py`
- `config/windmill/scripts/calibrate-triage-rules.py`
- `config/workflow-catalog.json`
- `Makefile`
- `docs/runbooks/incident-triage-engine.md`
- `docs/adr/0114-rule-based-incident-triage-engine.md`
- `docs/workstreams/adr-0114-incident-triage-engine.md`

## Expected Live Surfaces

- Running `python3 config/windmill/scripts/run-triage.py` with an alert payload produces a triage report and writes it under `.local/triage/reports/`
- When `LV3_TRIAGE_MATTERMOST_WEBHOOK_URL` is configured, the wrapper posts a summary to the incidents channel webhook
- The triage report is written as a `triage.report_created` event in the mutation-audit sink
- The weekly calibration wrapper writes `.local/triage/calibration/latest.json`

## Verification

- Run `uv run --with pytest --with pyyaml python -m pytest tests/test_incident_triage.py tests/test_triage_windmill.py -q` → all tests pass
- Run `uv run --with pyyaml python scripts/validate_repository_data_models.py --validate` → triage config contracts validate
- Run `python3 scripts/incident_triage.py --service netbox --alert-name netbox_health_probe_failed --signal recent_deployment_within_2h=true` → report JSON contains at least one hypothesis
- Run `python3 config/windmill/scripts/run-triage.py` from a worker checkout with a payload → report is emitted successfully

## Merge Criteria

- Unit tests pass
- Triage config contracts validate through the repository data-model gate
- At least 6 rules exist in the initial `triage-rules.yaml`
- Windmill wrappers for report generation and calibration both return successful payloads from a mounted repo checkout

## Notes For The Next Assistant

- The triage engine intentionally lives under `scripts/` rather than a new top-level `platform/` package so it does not shadow Python's stdlib `platform` module
- The Loki signal extraction (`error_log_count_15m`) uses the LogQL HTTP API directly when `LV3_TRIAGE_LOKI_QUERY_URL` is configured
- The auto-check executor is observation-only and gated by `config/triage-auto-check-allowlist.yaml`
- Calibration joins triage reports against resolved cases by `incident_id`; until ADR 0118 exists live, the wrapper returns `insufficient_data` cleanly when no case file is present
