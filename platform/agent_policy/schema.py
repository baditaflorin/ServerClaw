from __future__ import annotations

from dataclasses import asdict, dataclass, field
from platform.enum_compat import StrEnum
from typing import Any

class TrustTier(StrEnum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


class PolicyOutcome(StrEnum):
    ALLOW = "allow"
    ESCALATE = "escalate"
    DENY = "deny"


@dataclass(frozen=True)
class AutonomousActionPolicy:
    max_risk_class: str
    allowed_workflow_tags: list[str] = field(default_factory=list)
    disallowed_workflow_ids: list[str] = field(default_factory=list)
    max_daily_autonomous_executions: int = 0


@dataclass(frozen=True)
class EscalationPolicy:
    on_risk_above: str
    escalation_target: str
    escalation_event: str


@dataclass(frozen=True)
class AgentPolicy:
    agent_id: str
    description: str
    identity_class: str
    trust_tier: TrustTier
    read_surfaces: list[str]
    autonomous_actions: AutonomousActionPolicy
    escalation: EscalationPolicy


@dataclass(frozen=True)
class WorkflowCapability:
    workflow_id: str
    execution_class: str
    live_impact: str
    required_read_surfaces: list[str]
    tags: list[str]


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    reason: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    escalation_target: str | None = None
    escalation_event: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcome"] = self.outcome.value
        return payload
