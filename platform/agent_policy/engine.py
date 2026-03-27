from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from .schema import (
    AgentPolicy,
    AutonomousActionPolicy,
    EscalationPolicy,
    PolicyDecision,
    PolicyOutcome,
    TrustTier,
    WorkflowCapability,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "agent-policies.yaml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
DEFAULT_COUNTER_PATH = REPO_ROOT / ".local" / "state" / "agent-policy" / "daily-autonomous-executions.json"
RISK_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}
ACTOR_ID_ALIASES = {
    "operator:lv3_cli": "operator:lv3-cli",
}


def normalize_actor_id(actor_id: str) -> str:
    normalized = actor_id.strip()
    return ACTOR_ID_ALIASES.get(normalized, normalized)


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def normalize_risk_class(value: Any) -> str:
    normalized = str(getattr(value, "value", value)).strip().upper()
    if normalized not in RISK_RANK:
        raise ValueError(f"unsupported risk class '{value}'")
    return normalized


def _risk_rank(value: Any) -> int:
    return RISK_RANK[normalize_risk_class(value)]


def infer_workflow_tags(workflow_id: str, workflow: dict[str, Any]) -> list[str]:
    tags = {
        str(tag).strip()
        for tag in workflow.get("tags", [])
        if isinstance(tag, str) and str(tag).strip()
    }
    execution_class = str(workflow.get("execution_class", "")).strip()
    if execution_class == "diagnostic":
        tags.add("diagnostic")
    elif execution_class:
        tags.add(execution_class)
    if workflow_id.startswith("converge-"):
        tags.add("converge")
    if workflow_id.startswith("rotate-secret"):
        tags.add("rotate_secret")
    if workflow_id.startswith("run-triage"):
        tags.add("auto_check")
    if workflow_id.startswith("validate"):
        tags.add("validation")
    return sorted(tags)


def load_agent_policies(*, repo_root: Path | None = None) -> dict[str, AgentPolicy]:
    root = repo_root or REPO_ROOT
    path = root / "config" / "agent-policies.yaml"
    payload = _load_yaml(path)
    entries = payload if isinstance(payload, list) else []
    policies: dict[str, AgentPolicy] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        agent_id = normalize_actor_id(str(item.get("agent_id", "")).strip())
        if not agent_id:
            continue
        autonomous_payload = item.get("autonomous_actions", {})
        escalation_payload = item.get("escalation", {})
        policies[agent_id] = AgentPolicy(
            agent_id=agent_id,
            description=str(item.get("description", "")).strip(),
            identity_class=str(item.get("identity_class", "")).strip(),
            trust_tier=TrustTier(str(item.get("trust_tier", "T1")).strip()),
            read_surfaces=[
                str(surface).strip()
                for surface in item.get("read_surfaces", [])
                if isinstance(surface, str) and str(surface).strip()
            ],
            autonomous_actions=AutonomousActionPolicy(
                max_risk_class=normalize_risk_class(autonomous_payload.get("max_risk_class", "LOW")),
                allowed_workflow_tags=[
                    str(tag).strip()
                    for tag in autonomous_payload.get("allowed_workflow_tags", [])
                    if isinstance(tag, str) and str(tag).strip()
                ],
                disallowed_workflow_ids=[
                    str(workflow_id).strip()
                    for workflow_id in autonomous_payload.get("disallowed_workflow_ids", [])
                    if isinstance(workflow_id, str) and str(workflow_id).strip()
                ],
                max_daily_autonomous_executions=int(
                    autonomous_payload.get("max_daily_autonomous_executions", 0)
                ),
            ),
            escalation=EscalationPolicy(
                on_risk_above=normalize_risk_class(escalation_payload.get("on_risk_above", "LOW")),
                escalation_target=str(escalation_payload.get("escalation_target", "")).strip(),
                escalation_event=str(escalation_payload.get("escalation_event", "")).strip(),
            ),
        )
    return policies


def load_policy_for_actor(actor_id: str, *, repo_root: Path | None = None) -> AgentPolicy:
    normalized = normalize_actor_id(actor_id)
    policies = load_agent_policies(repo_root=repo_root)
    if normalized not in policies:
        raise KeyError(f"no agent policy defined for '{normalized}'")
    return policies[normalized]


def load_workflow_capability(
    workflow_id: str,
    *,
    repo_root: Path | None = None,
    workflow: dict[str, Any] | None = None,
) -> WorkflowCapability:
    root = repo_root or REPO_ROOT
    entry = workflow
    if entry is None:
        payload = json.loads((root / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
        workflows = payload.get("workflows", {})
        entry = workflows.get(workflow_id)
        if not isinstance(entry, dict):
            entry = {}
    required_read_surfaces = [
        str(surface).strip()
        for surface in entry.get("required_read_surfaces", [])
        if isinstance(surface, str) and str(surface).strip()
    ]
    execution_class = str(entry.get("execution_class", "")).strip()
    if not execution_class:
        execution_class = "diagnostic" if str(entry.get("live_impact", "")).strip() == "repo_only" else "mutation"
    return WorkflowCapability(
        workflow_id=workflow_id,
        execution_class=execution_class,
        live_impact=str(entry.get("live_impact", "guest_live")).strip(),
        required_read_surfaces=sorted(set(required_read_surfaces)),
        tags=infer_workflow_tags(workflow_id, entry),
    )


class DailyExecutionCounter:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_COUNTER_PATH

    def _load(self) -> dict[str, dict[str, int]]:
        if not self._path.exists():
            return {}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {
            str(day): {
                str(actor_id): int(count)
                for actor_id, count in counters.items()
                if isinstance(actor_id, str) and isinstance(count, int)
            }
            for day, counters in payload.items()
            if isinstance(day, str) and isinstance(counters, dict)
        }

    def _store(self, payload: dict[str, dict[str, int]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _day_key(day: date | None = None) -> str:
        value = day or datetime.now(UTC).date()
        return value.isoformat()

    def get(self, actor_id: str, *, day: date | None = None) -> int:
        payload = self._load()
        return int(payload.get(self._day_key(day), {}).get(normalize_actor_id(actor_id), 0))

    def increment(self, actor_id: str, *, day: date | None = None) -> int:
        payload = self._load()
        day_key = self._day_key(day)
        actor_key = normalize_actor_id(actor_id)
        counters = payload.setdefault(day_key, {})
        counters[actor_key] = int(counters.get(actor_key, 0)) + 1
        self._store(payload)
        return counters[actor_key]


class AgentPolicyEngine:
    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or REPO_ROOT

    def load_policy(self, actor_id: str) -> AgentPolicy:
        return load_policy_for_actor(actor_id, repo_root=self._repo_root)

    def load_workflow(self, workflow_id: str) -> WorkflowCapability:
        return load_workflow_capability(workflow_id, repo_root=self._repo_root)

    def evaluate(
        self,
        *,
        actor_id: str,
        workflow_id: str,
        risk_class: Any,
        required_read_surfaces: list[str] | None = None,
        autonomous: bool,
        current_daily_executions: int | None = None,
    ) -> PolicyDecision:
        policy = self.load_policy(actor_id)
        workflow = self.load_workflow(workflow_id)
        normalized_risk_class = normalize_risk_class(risk_class)
        required_surfaces = sorted(set((required_read_surfaces or []) + workflow.required_read_surfaces))
        missing_surfaces = sorted(set(required_surfaces) - set(policy.read_surfaces))
        if missing_surfaces:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="surface_access_denied",
                message=(
                    f"{policy.agent_id} cannot read required surface(s): {', '.join(missing_surfaces)}"
                ),
                metadata={"missing_surfaces": missing_surfaces, "required_surfaces": required_surfaces},
            )
        if workflow_id in policy.autonomous_actions.disallowed_workflow_ids:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="workflow_disallowed",
                message=f"{policy.agent_id} is prohibited from running workflow '{workflow_id}'",
                metadata={"workflow_id": workflow_id},
            )
        allowed_tags = set(policy.autonomous_actions.allowed_workflow_tags)
        workflow_tags = set(workflow.tags)
        if allowed_tags and not workflow_tags.intersection(allowed_tags):
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="workflow_tag_not_allowed",
                message=(
                    f"{policy.agent_id} may run tags {sorted(allowed_tags)} but "
                    f"'{workflow_id}' exposes {sorted(workflow_tags) or ['none']}"
                ),
                metadata={
                    "workflow_id": workflow_id,
                    "workflow_tags": sorted(workflow_tags),
                    "allowed_workflow_tags": sorted(allowed_tags),
                },
            )
        if autonomous and current_daily_executions is not None:
            if current_daily_executions >= policy.autonomous_actions.max_daily_autonomous_executions:
                return PolicyDecision(
                    outcome=PolicyOutcome.DENY,
                    reason="daily_autonomous_limit_reached",
                    message=(
                        f"{policy.agent_id} reached its daily autonomous execution cap "
                        f"({policy.autonomous_actions.max_daily_autonomous_executions})"
                    ),
                    metadata={
                        "current_daily_executions": current_daily_executions,
                        "max_daily_autonomous_executions": policy.autonomous_actions.max_daily_autonomous_executions,
                    },
                )
        if autonomous and _risk_rank(risk_class) > _risk_rank(policy.autonomous_actions.max_risk_class):
            return PolicyDecision(
                outcome=PolicyOutcome.ESCALATE,
                reason="capability_bound_exceeded",
                message=(
                    f"{policy.agent_id} may only run up to {policy.autonomous_actions.max_risk_class} "
                    f"autonomously; '{workflow_id}' is {normalized_risk_class}"
                ),
                escalation_target=policy.escalation.escalation_target,
                escalation_event=policy.escalation.escalation_event,
                metadata={
                    "workflow_id": workflow_id,
                    "risk_class": normalized_risk_class,
                    "max_risk_class": policy.autonomous_actions.max_risk_class,
                },
            )
        return PolicyDecision(
            outcome=PolicyOutcome.ALLOW,
            reason="allowed",
            message=f"{policy.agent_id} is allowed to run '{workflow_id}'",
            metadata={
                "workflow_id": workflow_id,
                "workflow_tags": workflow.tags,
                "required_surfaces": required_surfaces,
            },
        )
