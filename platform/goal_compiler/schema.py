from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class RiskClass(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class RiskScore:
    source: str
    value: int
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IntentTarget:
    kind: str
    name: str
    services: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    vmids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class IntentScope:
    allowed_hosts: list[str] = field(default_factory=list)
    allowed_services: list[str] = field(default_factory=list)
    allowed_vmids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionIntent:
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
    execution_mode: str = "pessimistic"
    compensating_workflow_id: str | None = None
    rollback_window_seconds: int | None = None
    required_read_surfaces: list[str] = field(default_factory=list)
    required_lanes: list[str] = field(default_factory=list)
    risk_score: RiskScore | None = None
    resource_claims: list[dict[str, Any]] = field(default_factory=list)
    conflict_warnings: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_class"] = self.risk_class.value
        if self.risk_score is None:
            payload.pop("risk_score", None)
        return payload
