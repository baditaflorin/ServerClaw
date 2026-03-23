# Workstream ADR 0114: Rule-Based Incident Triage Engine

- ADR: [ADR 0114](../adr/0114-rule-based-incident-triage-engine.md)
- Title: CPU-only triage engine triggered on every firing alert — assembles signals from world state, evaluates ranked rules, posts hypotheses and cheapest first action to Mattermost before any operator acts
- Status: ready
- Branch: `codex/adr-0114-triage-engine`
- Worktree: `../proxmox_florin_server-triage-engine`
- Owner: codex
- Depends On: `adr-0052-loki-logs`, `adr-0057-mattermost-chatops`, `adr-0058-nats-event-bus`, `adr-0061-glitchtip`, `adr-0064-health-probe-contracts`, `adr-0097-alerting-routing`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`, `adr-0117-dependency-graph-runtime`
- Conflicts With: none
- Shared Surfaces: `platform/triage/`, `config/triage-rules.yaml`, Windmill triage workflow, `ledger.events`

## Scope

- create `platform/triage/__init__.py`, `platform/triage/engine.py` — context assembly, signal extraction, rule evaluation, hypothesis ranking
- create `platform/triage/rules.py` — YAML rule table loader, AND/OR condition evaluator, confidence scorer
- create `platform/triage/signals.py` — named signal extractors for all signal types defined in ADR 0114
- create `config/triage-rules.yaml` — initial rule set with at minimum: `recent-deployment-regression`, `upstream-db-saturation`, `tls-cert-expiry`, `resource-exhaustion`, `dependency-failure`, `configuration-drift`
- create `windmill/triage/run-triage.py` — Windmill workflow that receives an alert payload, calls the triage engine, and emits output
- configure Windmill subscription on `alerts.fired` NATS topic to trigger `run-triage` workflow
- configure the triage workflow to post the Mattermost triage report to `#platform-incidents`
- create `windmill/triage/calibrate-rules.py` — weekly workflow that computes per-rule precision/recall and posts to `#platform-ops`
- write `tests/unit/test_triage_engine.py` — unit tests for rule evaluation and signal extraction

## Non-Goals

- Autonomous remediation (unless `auto_check: true` for a specific discriminating check) — triage proposes, humans decide
- Writing the case library integration (ADR 0118) — that workstream adds the `similar_cases` block to triage reports once the case library exists
- Writing the alert routing rules (ADR 0097) — this workstream consumes the alert events that ADR 0097 fires

## Expected Repo Surfaces

- `platform/triage/__init__.py`
- `platform/triage/engine.py`
- `platform/triage/rules.py`
- `platform/triage/signals.py`
- `config/triage-rules.yaml`
- `windmill/triage/run-triage.py`
- `windmill/triage/calibrate-rules.py`
- `docs/adr/0114-rule-based-incident-triage-engine.md`
- `docs/workstreams/adr-0114-incident-triage-engine.md`

## Expected Live Surfaces

- Firing a test alert via `lv3 alert test netbox_health_probe_failed` triggers a Windmill triage job
- Within 60 seconds the Mattermost `#platform-incidents` channel receives a triage report with at least one hypothesis
- The triage report is written as a `triage.report_created` event in `ledger.events`
- The weekly calibration workflow is scheduled in Windmill

## Verification

- Run `pytest tests/unit/test_triage_engine.py -v` → all tests pass
- Fire a simulated health probe failure for netbox: `lv3 alert test netbox_health_probe_failed`
- Confirm the triage report appears in Mattermost `#platform-incidents` within 60 seconds
- Confirm `SELECT * FROM ledger.events WHERE event_type = 'triage.report_created' LIMIT 1;` returns a row
- Confirm the triage report JSON contains at least one hypothesis with `confidence > 0`

## Merge Criteria

- Unit tests pass
- End-to-end triage flow verified: alert → Windmill job → Mattermost post → ledger event
- At least 6 rules in the initial `triage-rules.yaml`
- Calibration workflow scheduled and has run at least once (can be a manual trigger for merge)

## Notes For The Next Assistant

- The `run-triage` Windmill workflow must have a 120-second timeout budget in the workflow catalog — triage involves Loki queries which can be slow
- The Loki signal extraction (`error_log_count_15m`) must use the LogQL HTTP API directly, not `logcli`; the Windmill execution environment may not have `logcli` installed
- For the `auto_check: true` discriminating checks, implement a hard allowlist of safe-to-auto-run check types in `config/triage-auto-check-allowlist.yaml`; do not derive the allowlist from the rule table at runtime
- The `calibration` workflow joins triage reports against resolved cases by `incident_id`; cases must be created in ADR 0118 before calibration can produce meaningful precision/recall numbers — the calibration workflow should handle `no cases found` gracefully with a "insufficient data" output
