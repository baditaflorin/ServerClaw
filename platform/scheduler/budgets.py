from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
WORKFLOW_DEFAULTS_PATH = REPO_ROOT / "config" / "workflow-defaults.yaml"
ALLOWED_EXECUTION_CLASSES = {"mutation", "diagnostic"}
ALLOWED_ESCALATION_ACTIONS = {"notify_and_abort", "abort_silently", "escalate_to_operator"}
DIAGNOSTIC_WORKFLOWS = {
    "validate",
    "pre-push-gate",
    "gate-status",
    "post-merge-gate",
    "nightly-integration-tests",
    "run-triage",
    "triage-calibration",
    "continuous-drift-detection",
    "restore-verification",
    "security-posture-scan",
    "check-platform-drift",
    "quarterly-access-review",
}


@dataclass(frozen=True)
class WorkflowBudget:
    max_duration_seconds: int
    max_steps: int
    max_concurrent_instances: int
    max_touched_hosts: int
    max_restarts: int
    max_rollback_depth: int
    escalation_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_duration_seconds": self.max_duration_seconds,
            "max_steps": self.max_steps,
            "max_concurrent_instances": self.max_concurrent_instances,
            "max_touched_hosts": self.max_touched_hosts,
            "max_restarts": self.max_restarts,
            "max_rollback_depth": self.max_rollback_depth,
            "escalation_action": self.escalation_action,
        }


@dataclass(frozen=True)
class WorkflowPolicy:
    workflow_id: str
    execution_class: str
    live_impact: str
    budget: WorkflowBudget
    workflow: dict[str, Any]


@dataclass(frozen=True)
class HostTouchEstimate:
    count: int
    advisory_only: bool
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "advisory_only": self.advisory_only,
            "source": self.source,
        }


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError(f"{path} must define a top-level workflows object")
    return workflows


def _require_int(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def _validate_budget_payload(payload: dict[str, Any], *, path: str) -> dict[str, Any]:
    escalation_action = payload.get("escalation_action")
    if escalation_action not in ALLOWED_ESCALATION_ACTIONS:
        raise ValueError(
            f"{path}.escalation_action must be one of {sorted(ALLOWED_ESCALATION_ACTIONS)}"
        )
    return {
        "max_duration_seconds": _require_int(payload.get("max_duration_seconds"), f"{path}.max_duration_seconds", minimum=1),
        "max_steps": _require_int(payload.get("max_steps"), f"{path}.max_steps", minimum=1),
        "max_concurrent_instances": _require_int(
            payload.get("max_concurrent_instances"),
            f"{path}.max_concurrent_instances",
            minimum=1,
        ),
        "max_touched_hosts": _require_int(payload.get("max_touched_hosts"), f"{path}.max_touched_hosts", minimum=0),
        "max_restarts": _require_int(payload.get("max_restarts"), f"{path}.max_restarts", minimum=0),
        "max_rollback_depth": _require_int(
            payload.get("max_rollback_depth"),
            f"{path}.max_rollback_depth",
            minimum=0,
        ),
        "escalation_action": escalation_action,
    }


def infer_execution_class(workflow_id: str, workflow: dict[str, Any]) -> str:
    value = workflow.get("execution_class")
    if isinstance(value, str) and value in ALLOWED_EXECUTION_CLASSES:
        return value
    if workflow_id in DIAGNOSTIC_WORKFLOWS:
        return "diagnostic"
    if str(workflow.get("live_impact", "")).strip() == "repo_only" and workflow_id not in {
        "install-hooks",
        "generate-status-docs",
    }:
        return "diagnostic"
    return "mutation"


def load_default_budget(
    *,
    repo_root: Path | None = None,
    defaults_path: Path | None = None,
) -> WorkflowBudget:
    path = defaults_path or (repo_root or REPO_ROOT) / "config" / "workflow-defaults.yaml"
    payload = _load_yaml(path)
    default_budget = payload.get("default_budget")
    if not isinstance(default_budget, dict):
        raise ValueError(f"{path} must define a default_budget mapping")
    normalized = _validate_budget_payload(default_budget, path=f"{path}.default_budget")
    return WorkflowBudget(**normalized)


def load_workflow_policy(
    workflow_id: str,
    *,
    repo_root: Path | None = None,
    catalog_path: Path | None = None,
    defaults_path: Path | None = None,
) -> WorkflowPolicy:
    root = repo_root or REPO_ROOT
    workflows = _load_catalog(catalog_path or root / "config" / "workflow-catalog.json")
    workflow = workflows.get(workflow_id)
    if not isinstance(workflow, dict):
        raise KeyError(f"unknown workflow '{workflow_id}'")

    defaults = load_default_budget(repo_root=root, defaults_path=defaults_path).as_dict()
    override = workflow.get("budget", {})
    if override is None:
        override = {}
    if not isinstance(override, dict):
        raise ValueError(f"workflow '{workflow_id}' budget must be a mapping")
    merged = {**defaults, **override}
    normalized = _validate_budget_payload(merged, path=f"workflow.{workflow_id}.budget")
    execution_class = infer_execution_class(workflow_id, workflow)
    if execution_class not in ALLOWED_EXECUTION_CLASSES:
        raise ValueError(
            f"workflow '{workflow_id}' execution_class must be one of {sorted(ALLOWED_EXECUTION_CLASSES)}"
        )
    return WorkflowPolicy(
        workflow_id=workflow_id,
        execution_class=execution_class,
        live_impact=str(workflow.get("live_impact", "guest_live")),
        budget=WorkflowBudget(**normalized),
        workflow=workflow,
    )


def estimate_touched_hosts(intent: Any, policy: WorkflowPolicy) -> HostTouchEstimate:
    arguments = getattr(intent, "arguments", {}) or {}
    for key in ("touched_hosts", "target_hosts", "hosts"):
        value = arguments.get(key)
        if isinstance(value, list):
            return HostTouchEstimate(
                count=len({str(item) for item in value if str(item).strip()}),
                advisory_only=False,
                source=f"arguments.{key}",
            )

    for key in ("host", "vm", "vm_name", "target_vm"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return HostTouchEstimate(count=1, advisory_only=True, source=f"arguments.{key}")

    target_vm = getattr(intent, "target_vm", None)
    if isinstance(target_vm, str) and target_vm.strip():
        return HostTouchEstimate(count=1, advisory_only=True, source="intent.target_vm")

    if policy.live_impact == "host_and_guest_live":
        return HostTouchEstimate(count=2, advisory_only=True, source="workflow.live_impact")
    if policy.live_impact in {"guest_live", "host_live", "external_live"}:
        return HostTouchEstimate(count=1, advisory_only=True, source="workflow.live_impact")
    return HostTouchEstimate(count=0, advisory_only=True, source="workflow.live_impact")
