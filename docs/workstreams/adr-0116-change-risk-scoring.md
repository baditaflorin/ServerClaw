# Workstream ADR 0116: Change Risk Scoring Without LLMs

- ADR: [ADR 0116](../adr/0116-change-risk-scoring.md)
- Title: Deterministic weighted arithmetic risk scorer — takes an ExecutionIntent and live platform context, returns a 0–100 score and RiskClass used to gate approvals and autonomous execution
- Status: ready
- Branch: `codex/adr-0116-risk-scoring`
- Worktree: `../proxmox_florin_server-risk-scoring`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0080-maintenance-windows`, `adr-0112-goal-compiler`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`, `adr-0117-dependency-graph-runtime`
- Conflicts With: none
- Shared Surfaces: `platform/risk_scorer/`, `config/risk-scoring-weights.yaml`

## Scope

- create `platform/risk_scorer/__init__.py`
- create `platform/risk_scorer/engine.py` — `score_intent()` function implementing the weighted arithmetic formula from ADR 0116
- create `platform/risk_scorer/dimensions.py` — one function per scoring dimension: `criticality_score()`, `fanout_score()`, `failure_rate_score()`, `surface_score()`, `rollback_score()`, `maintenance_score()`, `incident_score()`, `recency_score()`
- create `platform/risk_scorer/context.py` — `ScoringContext` dataclass and `assemble_context(intent, world_state, graph, ledger)` factory
- create `config/risk-scoring-weights.yaml` — initial weights and approval threshold config from ADR 0116
- create `windmill/risk-scoring/calibrate-weights.py` — weekly calibration workflow: queries ledger for recent changes, computes false positive/negative rates, posts to Mattermost
- update `platform/goal_compiler/compiler.py` — call risk scorer after compilation; embed `RiskScore` in `ExecutionIntent`; use higher of `rule_risk_class` and `computed_risk_class`
- write `tests/unit/test_risk_scorer.py` — test each scoring dimension independently; test classification thresholds; test stale-context penalty

## Non-Goals

- Writing the dependency graph traversal (ADR 0117) — `ScoringContext.downstream_count` will use a stub that reads from a config fallback until ADR 0117 is complete
- Deciding whether to execute — that gate belongs to the scheduler (ADR 0119)

## Expected Repo Surfaces

- `platform/risk_scorer/__init__.py`
- `platform/risk_scorer/engine.py`
- `platform/risk_scorer/dimensions.py`
- `platform/risk_scorer/context.py`
- `config/risk-scoring-weights.yaml`
- `windmill/risk-scoring/calibrate-weights.py`
- `platform/goal_compiler/compiler.py` (patched: risk scorer call added)
- `docs/adr/0116-change-risk-scoring.md`
- `docs/workstreams/adr-0116-change-risk-scoring.md`

## Expected Live Surfaces

- `lv3 run "deploy netbox"` displays a risk score and risk class in the compiled intent summary
- `lv3 run "deploy proxmox-host-lv3"` (a CRITICAL tier target) scores >= 75 and shows a `BLOCK` gate
- The weekly calibration workflow is scheduled in Windmill

## Verification

- Run `pytest tests/unit/test_risk_scorer.py -v` → all tests pass
- Run `lv3 run "rotate secret for openbao" --dry-run` → confirm a HIGH or CRITICAL risk class is shown
- Run `lv3 run "restart uptime-kuma"` during an active maintenance window → confirm score is lower than the same command outside a maintenance window
- Confirm `RiskScore` is embedded in the `intent.compiled` ledger event metadata

## Merge Criteria

- Unit tests pass including stale-context penalty test
- `lv3 run` interactive flow shows risk score in the compiled intent display
- At least one BLOCK-class intent tested manually and confirmed to halt before reaching Windmill
- Calibration workflow scheduled

## Notes For The Next Assistant

- The `downstream_count` dimension uses `DependencyGraphClient().descendants()` (ADR 0117). Until that workstream is merged, stub it as `config/risk-scoring-overrides.yaml` with a per-service fallback count. The stub should log a warning so the gap is visible.
- The `expected_change_count` dimension uses `SemanticDiff.total_changes` from ADR 0120. Until that workstream is merged, default it to 5 (the midpoint of the score range) to avoid producing artificially low scores.
- The calibration workflow should handle division-by-zero gracefully: if there are no changes in a risk class bucket during the lookback window, report "no data" for that bucket rather than crashing.
- Do not hard-code the `proxmox-host-lv3` host as CRITICAL in the scorer; read criticality from the service capability catalog (ADR 0075) via the world-state snapshot.
