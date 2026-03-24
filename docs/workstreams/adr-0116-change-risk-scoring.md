# Workstream ADR 0116: Change Risk Scoring Without LLMs

- ADR: [ADR 0116](../adr/0116-change-risk-scoring.md)
- Title: Deterministic weighted arithmetic risk scorer for compiled `lv3 run` workflow intents
- Status: merged
- Branch: `codex/adr-0116-risk-scoring`
- Worktree: `.worktrees/adr-0116`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0080-maintenance-windows`, `adr-0112-goal-compiler`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`, `adr-0117-dependency-graph-runtime`
- Conflicts With: none
- Shared Surfaces: `scripts/risk_scorer/`, `scripts/lv3_cli.py`, `config/risk-scoring-weights.yaml`, `config/risk-scoring-overrides.yaml`

## Scope

- create `scripts/risk_scorer/__init__.py`
- create `scripts/risk_scorer/engine.py` — `score_intent()` function implementing the weighted arithmetic formula from ADR 0116
- create `scripts/risk_scorer/dimensions.py` — one function per scoring dimension: `criticality_score()`, `fanout_score()`, `failure_rate_score()`, `surface_score()`, `rollback_score()`, `maintenance_score()`, `incident_score()`, `recency_score()`
- create `scripts/risk_scorer/context.py` — `ScoringContext` dataclass plus context assembly from workflow catalog, service catalog, receipts, maintenance windows, and overrides
- create `scripts/risk_scorer/models.py` — typed `ExecutionIntent`, `RiskClass`, and `RiskScore` structs for compiled workflow runs
- create `config/risk-scoring-weights.yaml` — initial weights and approval threshold config from ADR 0116
- create `config/risk-scoring-overrides.yaml` — canonical fallback tiers, downstream counts, and workflow defaults until ADRs 0117/0120 land
- create `config/windmill/scripts/calibrate-risk-scoring.py` — calibration workflow: scores recent live-apply receipts, computes false positive/negative rates, optionally posts to Mattermost
- update `scripts/lv3_cli.py` — compile workflow intents, display the YAML summary, and enforce `AUTO` / `SOFT` / `HARD` / `BLOCK` gates before calling Windmill
- write `tests/test_risk_scorer.py` — test each scoring dimension independently, classification thresholds, stale-context penalty, maintenance-window reduction, and CLI blocking behavior

## Non-Goals

- Writing the ADR 0112 goal compiler runtime — the scorer integrates with the current `lv3 run <workflow>` entrypoint until that surface exists
- Writing the dependency graph traversal (ADR 0117) — `ScoringContext.downstream_count` uses repo-managed fallback counts until ADR 0117 is complete
- Writing ledger-native persistence (ADR 0115) — the compiled CLI summary holds the scoring context until the mutation ledger runtime exists

## Expected Repo Surfaces

- `scripts/risk_scorer/__init__.py`
- `scripts/risk_scorer/engine.py`
- `scripts/risk_scorer/dimensions.py`
- `scripts/risk_scorer/context.py`
- `scripts/risk_scorer/models.py`
- `config/risk-scoring-weights.yaml`
- `config/risk-scoring-overrides.yaml`
- `config/windmill/scripts/calibrate-risk-scoring.py`
- `scripts/lv3_cli.py`
- `tests/test_risk_scorer.py`
- `docs/adr/0116-change-risk-scoring.md`
- `docs/workstreams/adr-0116-change-risk-scoring.md`
- `docs/runbooks/change-risk-scoring.md`

## Expected Live Surfaces

- `lv3 run windmill_healthcheck --dry-run` displays a compiled intent summary including the scoring context and numeric risk score
- `lv3 run configure-network` resolves a CRITICAL target and shows a `BLOCK` gate before any Windmill call
- `lv3 run restart-uptime-kuma` scores lower inside an active maintenance window than outside it
- `config/windmill/scripts/calibrate-risk-scoring.py` can score recent receipts and emit the calibration report JSON

## Verification

- Run `uv run --with pytest python -m pytest tests/test_risk_scorer.py tests/test_lv3_cli.py -q` → all tests pass
- Run `uv run python -m py_compile scripts/lv3_cli.py scripts/risk_scorer/*.py config/windmill/scripts/calibrate-risk-scoring.py` → Python entry points compile
- Run `lv3 run configure-network` → confirm the CLI blocks before calling Windmill unless `--risk-override` is supplied
- Run `lv3 run restart-uptime-kuma --dry-run` with and without an active maintenance window → confirm the score decreases during the window

## Merge Criteria

- Focused unit and CLI tests pass including the stale-context penalty test
- `lv3 run` shows the compiled intent YAML and risk score before calling Windmill
- At least one BLOCK-class workflow is confirmed to halt before any Windmill request is submitted
- The calibration script handles empty buckets by reporting `no data` instead of crashing

## Notes For The Next Assistant

- The downstream-count signal should be switched from `config/risk-scoring-overrides.yaml` to the ADR 0117 runtime when that module lands on `main`.
- ADR 0120 now supplies the expected-change-count signal for supported workflows. Keep workflow defaults only as a fallback for unsupported or unavailable diff surfaces.
- If ADR 0112 lands later, keep the existing `scripts/risk_scorer/` package and reuse it from the compiler rather than introducing a conflicting top-level `platform/` package.
