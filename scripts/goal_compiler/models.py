"""
Deterministic Goal Compiler — model layer (ADR 0112).

Defines the typed dataclasses that flow through the compilation pipeline:
  RawInstruction → CompiledIntent → YAML summary

These models are distinct from scripts/risk_scorer/models.py.  The risk-scorer
ExecutionIntent represents a workflow-level execution record; the goal-compiler
CompiledIntent represents the result of parsing a natural-language instruction
before it is handed to the execution layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskClass(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    def __str__(self) -> str:
        return self.value


RISK_RANK: dict[RiskClass, int] = {
    RiskClass.LOW: 1,
    RiskClass.MEDIUM: 2,
    RiskClass.HIGH: 3,
    RiskClass.CRITICAL: 4,
}


@dataclass(frozen=True)
class IntentTarget:
    """Resolved target for an intent (service, workflow, vmid, platform, …)."""

    kind: str
    name: str
    services: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    vmids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "services": list(self.services),
            "hosts": list(self.hosts),
            "vmids": list(self.vmids),
        }


@dataclass(frozen=True)
class IntentScope:
    """Allowed execution surface for an intent."""

    allowed_hosts: list[str] = field(default_factory=list)
    allowed_services: list[str] = field(default_factory=list)
    allowed_vmids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_services": list(self.allowed_services),
            "allowed_vmids": list(self.allowed_vmids),
        }


@dataclass(frozen=True)
class ScoringContext:
    """
    Lightweight scoring context passed to the risk scorer.

    The risk_scorer.ScoringContext requires many repo-level helpers (graph DSN,
    maintenance window tool, …).  This version is populated directly from
    catalog data during goal compilation and is sufficient for a compile-time
    risk estimate.
    """

    workflow_id: str
    target_service_id: str | None
    target_tier: str
    downstream_count: int
    recent_failure_rate: float
    expected_change_count: int
    irreversible_count: int
    unknown_count: int
    rollback_verified: bool
    in_maintenance_window: bool
    active_incident: bool
    hours_since_last_mutation: float | None
    stale: bool
    stale_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "target_service_id": self.target_service_id,
            "target_tier": self.target_tier,
            "downstream_count": self.downstream_count,
            "recent_failure_rate": round(self.recent_failure_rate, 3),
            "expected_change_count": self.expected_change_count,
            "irreversible_count": self.irreversible_count,
            "unknown_count": self.unknown_count,
            "rollback_verified": self.rollback_verified,
            "in_maintenance_window": self.in_maintenance_window,
            "active_incident": self.active_incident,
            "hours_since_last_mutation": (
                None if self.hours_since_last_mutation is None else round(self.hours_since_last_mutation, 2)
            ),
            "stale": self.stale,
            "stale_reasons": list(self.stale_reasons),
        }


@dataclass(frozen=True)
class CompiledIntent:
    """
    The fully-compiled form of an operator instruction.

    This is what the CLI serialises to YAML for pre-execution review and what
    is written to the ledger for every run.
    """

    id: str
    created_at: str
    raw_input: str
    action: str
    target: IntentTarget
    scope: IntentScope
    preconditions: list[str]
    risk_class: RiskClass
    allowed_tools: list[str]
    rollback_path: str | None
    success_criteria: list[str]
    ttl_seconds: int
    requires_approval: bool
    compiled_by: str
    # Risk-scorer integration fields
    workflow_id: str | None = None
    dispatch_payload: dict[str, Any] = field(default_factory=dict)
    risk_score: float | None = None
    risk_score_breakdown: dict[str, float] = field(default_factory=dict)
    scoring_context: dict[str, Any] = field(default_factory=dict)
    # Rule metadata
    matched_rule_id: str | None = None
    normalized_input: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "created_at": self.created_at,
            "raw_input": self.raw_input,
            "action": self.action,
            "target": self.target.as_dict(),
            "scope": self.scope.as_dict(),
            "preconditions": list(self.preconditions),
            "risk_class": str(self.risk_class),
            "allowed_tools": list(self.allowed_tools),
            "rollback_path": self.rollback_path,
            "success_criteria": list(self.success_criteria),
            "ttl_seconds": self.ttl_seconds,
            "requires_approval": self.requires_approval,
            "compiled_by": self.compiled_by,
        }
        if self.workflow_id is not None:
            d["workflow_id"] = self.workflow_id
        if self.dispatch_payload:
            d["dispatch_payload"] = self.dispatch_payload
        if self.risk_score is not None:
            d["risk_score"] = round(self.risk_score, 2)
        if self.risk_score_breakdown:
            d["risk_score_breakdown"] = {k: round(v, 2) for k, v in self.risk_score_breakdown.items()}
        if self.scoring_context:
            d["scoring_context"] = self.scoring_context
        if self.matched_rule_id is not None:
            d["matched_rule_id"] = self.matched_rule_id
        if self.normalized_input is not None:
            d["normalized_input"] = self.normalized_input
        return d
