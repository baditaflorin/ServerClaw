# ADR 0116: Change Risk Scoring Without LLMs

- Status: Accepted
- Implementation Status: Partial Implemented
- Implemented In Repo Version: 0.112.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The goal compiler (ADR 0112) assigns a `risk_class` to every compiled intent using a static rule table. Rule-table risk classes are coarse: they say "deploying any service is MEDIUM risk" without accounting for whether the target service has 0 or 5 downstream dependents, whether there is an active incident, whether the last three deployments of that service failed, or whether the deployment is happening at 2 AM on a Sunday.

The platform has all the data needed to compute risk precisely — in the world-state materializer (ADR 0113), the dependency graph (ADR 0117), and the mutation ledger (ADR 0115). What is missing is a scoring engine that reads these data sources and produces a numeric risk score per intent.

Risk scoring is critical for two platform capabilities:

1. **Autonomous execution**: low-risk, routine changes (health probe restarts, certificate renewals, configuration drift corrections) should run without operator approval. Without a reliable risk score, either everything requires approval (too slow) or everything auto-runs (too dangerous).
2. **Change gating**: the validation gate (ADR 0087) enforces syntax and schema checks. It does not currently block a deployment to a critical service during an active incident.

## Decision

We will implement a **deterministic change risk scoring engine** as a Python module at `scripts/risk_scorer/` that computes a numeric risk score (0–100) and a derived `RiskClass` (LOW / MEDIUM / HIGH / CRITICAL) for every compiled `ExecutionIntent`.

The ADR originally proposed a top-level Python package named `platform/`. In this repository that would shadow Python's standard-library `platform` module under normal test and CLI execution. The implemented path therefore uses `scripts/risk_scorer/` while keeping the scoring contract, weights, and context model described below.

### Scoring dimensions

Each dimension contributes a weighted sub-score. Weights are configured in `config/risk-scoring-weights.yaml` and are adjustable without code changes.

| Dimension | Description | Max contribution | Default weight |
|---|---|---|---|
| Target criticality | Criticality tier of the target service/host (ADR 0075 capability catalog) | 30 | 1.0 |
| Dependency fanout | Number of services downstream of the target (ADR 0117 graph) | 20 | 1.0 |
| Historical failure rate | Fraction of last 10 deployments to this target that failed (ADR 0115 ledger) | 15 | 1.0 |
| Mutation surface | Number of distinct objects the intent is expected to change (ADR 0120 diff) | 10 | 1.0 |
| Rollback confidence | Does the compiled intent have a verified rollback path? (0=no, 1=yes) | 10 | 1.0 |
| Maintenance window | Is a maintenance window active for the target? (0=outside, 1=inside) | -15 | 1.0 |
| Active incident | Is there a currently open incident for the target or its dependents? | 20 | 1.0 |
| Recency of last change | Hours since the last mutation to this target; very recent = higher risk | 5 | 1.0 |

### Scoring formula

```python
# scripts/risk_scorer/engine.py

def score_intent(intent: ExecutionIntent, ctx: ScoringContext) -> RiskScore:
    weights = load_weights("config/risk-scoring-weights.yaml")

    raw = (
        weights["target_criticality"]   * criticality_score(ctx.target_tier)        +
        weights["dependency_fanout"]    * fanout_score(ctx.downstream_count)         +
        weights["historical_failure"]   * failure_rate_score(ctx.recent_failure_rate)+
        weights["mutation_surface"]     * surface_score(ctx.expected_change_count)   +
        weights["rollback_confidence"]  * rollback_score(intent.rollback_path)       +
        weights["maintenance_window"]   * maintenance_score(ctx.in_maintenance_window)+
        weights["active_incident"]      * incident_score(ctx.active_incident)        +
        weights["recency"]              * recency_score(ctx.hours_since_last_mutation)
    )

    score = max(0, min(100, raw))
    risk_class = classify(score)  # LOW<25, MEDIUM<50, HIGH<75, CRITICAL>=75

    return RiskScore(
        score=score,
        risk_class=risk_class,
        dimension_breakdown=...,
        scoring_version=weights["version"],
    )
```

The score is deterministic for the same input context. A scoring context snapshot is embedded in the compiled `ExecutionIntent` summary so that risk scores are reproducible during audit and replay.

### Integration with `lv3 run`

The current repository does not yet ship the ADR 0112 goal-compiler runtime. The implemented integration point is therefore the existing `lv3 run <workflow>` CLI path from ADR 0090.

Before the CLI calls the Windmill API, it now:

1. builds a typed `ExecutionIntent` for the requested workflow invocation
2. assembles a deterministic scoring context from repo-managed catalogs, live-apply receipts, and maintenance-window state
3. computes both the static rule risk class and the numeric risk score
4. displays the compiled intent YAML including the scoring context and risk breakdown
5. enforces the stricter of the rule-derived and computed risk classes before submitting the workflow

If the scorer returns a higher risk class than the rule table assigned from `live_impact`, the scorer's value wins. The compiled summary records both `rule_risk_class` and `computed_risk_class`.

### Approval thresholds

```yaml
# config/risk-scoring-weights.yaml
approval_thresholds:
  auto_run_below: 25          # score < 25: execute without approval
  soft_gate_below: 50         # 25 <= score < 50: show operator the score, proceed unless cancelled
  hard_gate_below: 75         # 50 <= score < 75: require explicit operator approval
  block_above: 75             # score >= 75: block execution, require senior approval or override flag
```

### Score calibration

A Windmill-compatible calibration script at `config/windmill/scripts/calibrate-risk-scoring.py` queries recent live-apply receipts from the repository, recomputes their scores, and computes:

- **False negative rate**: fraction of LOW-scored changes that resulted in an incident.
- **False positive rate**: fraction of CRITICAL-scored changes that succeeded without incident.

These rates can be posted to Mattermost `#platform-ops` and are used by the operator to adjust weights. Weight adjustments are committed to `config/risk-scoring-weights.yaml` via the normal ADR/PR process.

## Consequences

**Positive**

- Automation is governed by math, not vibes. Low-risk routine changes (certificate renewal, probe restarts, drift corrections) run autonomously; high-risk changes are gated.
- The approval threshold table is transparent and adjustable without code changes.
- Score calibration surfaces whether the thresholds are set correctly; the operator can tune without rewriting rules.
- Scoring context is stored in the ledger, so every risk decision is auditable and replayable.

**Negative / Trade-offs**

- Initial scoring weights will be wrong. The first 30–60 days of operation will require regular weight tuning as false positive and negative rates surface.
- The mutation surface dimension now consumes ADR 0120 semantic diff output when the diff engine can compute a surface-specific prediction. Workflow defaults and overrides remain as fallback values for workflows whose surfaces are still unsupported or unavailable at compile time.
- The dependency fanout dimension still depends on ADR 0117 for live graph traversal. Until that runtime exists, the scorer uses `config/risk-scoring-overrides.yaml` fallback counts and marks the context as stale when a canonical signal is unavailable.

## Boundaries

- The risk scorer is a pure function of its input context. It does not modify any platform state.
- It does not call the Windmill API or mutate target services while scoring. Context is assembled from repository data, local receipt history, and the maintenance-window query surface.
- It does not use any LLM or statistical model. Scores are computed by weighted arithmetic over well-defined scalar inputs.

## Related ADRs

- ADR 0075: Service capability catalog (target criticality tier)
- ADR 0080: Maintenance windows (maintenance window signal)
- ADR 0087: Repository validation gate (change gating integration point)
- ADR 0112: Deterministic goal compiler (calls risk scorer; stores risk class in intent)
- ADR 0113: World-state materializer (provides active incident and recency signals)
- ADR 0115: Event-sourced mutation ledger (provides historical failure rate; receives scoring context)
- ADR 0117: Service dependency graph (provides dependency fanout)
- ADR 0119: Budgeted workflow scheduler (respects risk class for approval gating)
- ADR 0120: Dry-run semantic diff engine (provides mutation surface count)
