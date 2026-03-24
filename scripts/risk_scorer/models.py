from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from platform.diff_engine.schema import SemanticDiff


class RiskClass(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


RISK_CLASS_ORDER = {
    RiskClass.LOW: 0,
    RiskClass.MEDIUM: 1,
    RiskClass.HIGH: 2,
    RiskClass.CRITICAL: 3,
}


def max_risk_class(*classes: RiskClass) -> RiskClass:
    return max(classes, key=lambda item: RISK_CLASS_ORDER[item])


@dataclass(frozen=True)
class RiskScore:
    score: float
    risk_class: RiskClass
    final_risk_class: RiskClass
    approval_gate: str
    dimension_breakdown: dict[str, float]
    scoring_version: str
    stale: bool
    stale_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "risk_class": self.risk_class.value,
            "final_risk_class": self.final_risk_class.value,
            "approval_gate": self.approval_gate,
            "dimension_breakdown": {key: round(value, 2) for key, value in self.dimension_breakdown.items()},
            "scoring_version": self.scoring_version,
            "stale": self.stale,
            "stale_reasons": list(self.stale_reasons),
        }


@dataclass(frozen=True)
class ExecutionIntent:
    intent_id: str
    workflow_id: str
    workflow_description: str
    arguments: dict[str, Any]
    live_impact: str
    target_service_id: str | None
    target_vm: str | None
    rule_risk_class: RiskClass
    computed_risk_class: RiskClass
    final_risk_class: RiskClass
    requires_approval: bool
    rollback_verified: bool
    expected_change_count: int
    irreversible_count: int
    unknown_count: int
    scoring_context: dict[str, Any]
    risk_score: RiskScore
    semantic_diff: "SemanticDiff | None" = None
    resource_claims: list[dict[str, Any]] | None = None
    conflict_warnings: list[dict[str, Any]] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "intent_id": self.intent_id,
            "workflow_id": self.workflow_id,
            "description": self.workflow_description,
            "arguments": self.arguments,
            "live_impact": self.live_impact,
            "rule_risk_class": self.rule_risk_class.value,
            "computed_risk_class": self.computed_risk_class.value,
            "risk_class": self.final_risk_class.value,
            "requires_approval": self.requires_approval,
            "rollback_verified": self.rollback_verified,
            "expected_change_count": self.expected_change_count,
            "irreversible_count": self.irreversible_count,
            "unknown_count": self.unknown_count,
            "scoring_context": self.scoring_context,
            "risk_score": self.risk_score.as_dict(),
        }
        if self.semantic_diff is not None:
            payload["semantic_diff"] = self.semantic_diff.as_dict()
        if self.resource_claims:
            payload["resource_claims"] = self.resource_claims
        if self.conflict_warnings:
            payload["conflict_warnings"] = self.conflict_warnings
        if self.target_service_id:
            payload["target_service_id"] = self.target_service_id
        if self.target_vm:
            payload["target_vm"] = self.target_vm
        return payload
