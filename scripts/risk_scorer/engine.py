from __future__ import annotations

from typing import Any

from .context import ScoringContext, load_risk_scoring_weights
from .dimensions import (
    criticality_score,
    failure_rate_score,
    fanout_score,
    incident_score,
    maintenance_score,
    recency_score,
    rollback_score,
    surface_score,
)
from .models import ExecutionIntent, RiskClass, RiskScore, max_risk_class


def classify(score: float, thresholds: dict[str, Any] | None = None) -> RiskClass:
    limits = thresholds or {"low": 25, "medium": 50, "high": 75}
    if score < float(limits.get("low", 25)):
        return RiskClass.LOW
    if score < float(limits.get("medium", 50)):
        return RiskClass.MEDIUM
    if score < float(limits.get("high", 75)):
        return RiskClass.HIGH
    return RiskClass.CRITICAL


def approval_gate(score: float, final_risk_class: RiskClass, approval_thresholds: dict[str, Any]) -> str:
    block_above = float(approval_thresholds.get("block_above", 75))
    hard_gate_below = float(approval_thresholds.get("hard_gate_below", 75))
    soft_gate_below = float(approval_thresholds.get("soft_gate_below", 50))
    if score >= block_above or final_risk_class == RiskClass.CRITICAL:
        return "BLOCK"
    if score >= soft_gate_below or final_risk_class == RiskClass.HIGH:
        return "HARD"
    if score >= float(approval_thresholds.get("auto_run_below", 25)) or final_risk_class == RiskClass.MEDIUM:
        return "SOFT"
    if score >= hard_gate_below:
        return "HARD"
    return "AUTO"


def score_intent(
    intent: ExecutionIntent | dict[str, Any],
    ctx: ScoringContext,
    *,
    repo_root=None,
) -> RiskScore:
    payload = intent.as_dict() if isinstance(intent, ExecutionIntent) else intent
    config = load_risk_scoring_weights(repo_root)
    weights = config.get("weights", {})
    thresholds = config.get("classification_thresholds", {"low": 25, "medium": 50, "high": 75})
    defaults = config.get("defaults", {})

    breakdown = {
        "target_criticality": float(weights.get("target_criticality", 1.0)) * criticality_score(ctx.target_tier),
        "dependency_fanout": float(weights.get("dependency_fanout", 1.0)) * fanout_score(ctx.downstream_count),
        "historical_failure": float(weights.get("historical_failure", 1.0))
        * failure_rate_score(ctx.recent_failure_rate),
        "mutation_surface": float(weights.get("mutation_surface", 1.0))
        * surface_score(
            ctx.expected_change_count,
            irreversible_count=ctx.irreversible_count,
            unknown_count=ctx.unknown_count,
        ),
        "rollback_confidence": float(weights.get("rollback_confidence", 1.0)) * rollback_score(ctx.rollback_verified),
        "maintenance_window": float(weights.get("maintenance_window", 1.0)) * maintenance_score(ctx.in_maintenance_window),
        "active_incident": float(weights.get("active_incident", 1.0)) * incident_score(ctx.active_incident),
        "recency": float(weights.get("recency", 1.0)) * recency_score(ctx.hours_since_last_mutation),
    }
    if ctx.stale:
        breakdown["stale_context_penalty"] = float(weights.get("stale_context_penalty", 1.0)) * float(
            defaults.get("stale_context_penalty", 10)
        )
    raw = sum(breakdown.values())
    score = max(0.0, min(100.0, raw))
    computed_risk_class = classify(score, thresholds)
    rule_risk_class = payload.get("rule_risk_class", RiskClass.MEDIUM)
    if isinstance(rule_risk_class, str):
        rule_risk_class = RiskClass[str(rule_risk_class)]
    final_risk_class = max_risk_class(computed_risk_class, rule_risk_class)
    return RiskScore(
        score=score,
        risk_class=computed_risk_class,
        final_risk_class=final_risk_class,
        approval_gate=approval_gate(score, final_risk_class, config.get("approval_thresholds", {})),
        dimension_breakdown=breakdown,
        scoring_version=str(config.get("version", "1.0.0")),
        stale=ctx.stale,
        stale_reasons=ctx.stale_reasons,
    )
