from __future__ import annotations

import json
import os
import sys
from hashlib import sha1
from dataclasses import dataclass
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from controller_automation_toolkit import load_json, load_yaml, repo_path
from maintenance_window_tool import list_active_windows_best_effort
from platform.conflict import infer_resource_claims
from platform.execution_lanes import resolve_lanes
from platform.graph import DependencyGraphClient

from .models import ExecutionIntent, RiskClass


@dataclass(frozen=True)
class ScoringContext:
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
    signal_sources: dict[str, str]

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
            "hours_since_last_mutation": None
            if self.hours_since_last_mutation is None
            else round(self.hours_since_last_mutation, 2),
            "stale": self.stale,
            "stale_reasons": list(self.stale_reasons),
            "signal_sources": self.signal_sources,
        }


def load_risk_scoring_overrides(repo_root: Path | None = None) -> dict[str, Any]:
    base = repo_root or repo_path()
    path = base / "config" / "risk-scoring-overrides.yaml"
    if not path.exists():
        return {}
    payload = load_yaml(path)
    return payload if isinstance(payload, dict) else {}


def load_risk_scoring_weights(repo_root: Path | None = None) -> dict[str, Any]:
    base = repo_root or repo_path()
    path = base / "config" / "risk-scoring-weights.yaml"
    if not path.exists():
        return {
            "version": "1.0.0",
            "weights": {
                "target_criticality": 1.0,
                "dependency_fanout": 1.0,
                "historical_failure": 1.0,
                "mutation_surface": 1.0,
                "rollback_confidence": 1.0,
                "maintenance_window": 1.0,
                "active_incident": 1.0,
                "recency": 1.0,
                "stale_context_penalty": 1.0,
            },
            "approval_thresholds": {
                "auto_run_below": 25,
                "soft_gate_below": 50,
                "hard_gate_below": 75,
                "block_above": 75,
            },
            "defaults": {
                "expected_change_count": 5,
                "failure_lookback": 10,
                "hours_since_last_mutation_if_unknown": 72,
                "stale_context_penalty": 10,
            },
        }
    payload = load_yaml(path)
    return payload if isinstance(payload, dict) else {}


def workflow_catalog(repo_root: Path | None = None) -> dict[str, Any]:
    base = repo_root or repo_path()
    payload = load_json(base / "config" / "workflow-catalog.json")
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError("config/workflow-catalog.json must define a workflows object")
    return workflows


def service_catalog(repo_root: Path | None = None) -> dict[str, dict[str, Any]]:
    base = repo_root or repo_path()
    payload = load_json(base / "config" / "service-capability-catalog.json")
    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError("config/service-capability-catalog.json must define a services list")
    return {service["id"]: service for service in services}


def secret_owner_map(repo_root: Path | None = None) -> dict[str, str]:
    base = repo_root or repo_path()
    payload = load_json(base / "config" / "secret-catalog.json", default={})
    secrets = payload.get("secrets", [])
    if not isinstance(secrets, list):
        return {}
    mapping: dict[str, str] = {}
    for item in secrets:
        if not isinstance(item, dict):
            continue
        secret_id = item.get("id")
        owner_service = item.get("owner_service")
        if isinstance(secret_id, str) and isinstance(owner_service, str):
            mapping[secret_id] = owner_service
    return mapping


def resolve_rule_risk_class(live_impact: str) -> RiskClass:
    return {
        "repo_only": RiskClass.LOW,
        "guest_live": RiskClass.MEDIUM,
        "external_live": RiskClass.HIGH,
        "host_live": RiskClass.CRITICAL,
        "host_and_guest_live": RiskClass.CRITICAL,
    }.get(live_impact, RiskClass.MEDIUM)


def normalize_identifier(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def make_intent_id(workflow_id: str, arguments: dict[str, Any]) -> str:
    digest = sha1(json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
    return f"{workflow_id}:{digest}"


def infer_target_service_id(
    workflow_id: str,
    arguments: dict[str, Any],
    services: dict[str, dict[str, Any]],
    secret_owners: dict[str, str],
    overrides: dict[str, Any],
) -> str | None:
    workflow_defaults = overrides.get("workflow_defaults", {})
    if isinstance(workflow_defaults, dict):
        workflow_default = workflow_defaults.get(workflow_id)
        if isinstance(workflow_default, dict) and isinstance(workflow_default.get("target_service"), str):
            return normalize_identifier(workflow_default["target_service"])

    for key in ("service", "service_id", "target_service"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            candidate = normalize_identifier(value)
            if candidate in services:
                return candidate

    secret_id = arguments.get("secret_id")
    if isinstance(secret_id, str) and secret_id in secret_owners:
        return normalize_identifier(secret_owners[secret_id])

    normalized_workflow = normalize_identifier(workflow_id)
    for service_id in sorted(services, key=len, reverse=True):
        if service_id in normalized_workflow:
            return service_id

    if normalized_workflow.startswith("converge_"):
        candidate = normalized_workflow.removeprefix("converge_")
        if candidate in services:
            return candidate
    if normalized_workflow.startswith("configure_"):
        candidate = normalized_workflow.removeprefix("configure_")
        if candidate in services:
            return candidate

    default_host_service = overrides.get("default_host_service")
    if isinstance(default_host_service, str):
        return normalize_identifier(default_host_service)
    return None


def resolve_workflow_defaults(workflow_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    workflow_defaults = overrides.get("workflow_defaults", {})
    if not isinstance(workflow_defaults, dict):
        return {}
    candidate = workflow_defaults.get(workflow_id, {})
    return candidate if isinstance(candidate, dict) else {}


def resolve_target_tier(
    service_id: str | None,
    live_impact: str,
    services: dict[str, dict[str, Any]],
    overrides: dict[str, Any],
    stale_reasons: list[str],
) -> str:
    service_tiers = overrides.get("service_tiers", {})
    if service_id and isinstance(service_tiers, dict):
        tier = service_tiers.get(service_id)
        if isinstance(tier, str):
            return tier

    if service_id and service_id in services:
        category = str(services[service_id].get("category", "")).strip().lower()
        exposure = str(services[service_id].get("exposure", "")).strip().lower()
        if service_id in {"proxmox_ui", "openbao", "step_ca"}:
            stale_reasons.append(f"criticality tier for {service_id} inferred from service id")
            return "critical"
        if category in {"security", "infrastructure"}:
            stale_reasons.append(f"criticality tier for {service_id} inferred from service category")
            return "high"
        if exposure in {"edge-published", "edge-static"}:
            stale_reasons.append(f"criticality tier for {service_id} inferred from service exposure")
            return "high"
        stale_reasons.append(f"criticality tier for {service_id} defaulted to medium")
        return "medium"

    if live_impact in {"host_live", "host_and_guest_live"}:
        stale_reasons.append("criticality tier defaulted from live_impact")
        return "critical"
    if live_impact == "external_live":
        stale_reasons.append("criticality tier defaulted from live_impact")
        return "high"
    stale_reasons.append("criticality tier defaulted to medium")
    return "medium"


def dependency_graph_descendants(
    service_id: str,
    repo_root: Path | None,
    overrides: dict[str, Any],
    stale_reasons: list[str],
) -> int:
    if not service_id:
        return 0
    graph_dsn = os.environ.get("LV3_GRAPH_DSN", "").strip() or os.environ.get("WORLD_STATE_DSN", "").strip()
    if graph_dsn:
        try:
            client = DependencyGraphClient(dsn=graph_dsn)
            return len(
                [node_id for node_id in client.descendants(f"service:{service_id}") if node_id.startswith("service:")]
            )
        except Exception as exc:
            stale_reasons.append(f"dependency fanout for {service_id} fell back to repo graph because {exc}")
    base = repo_root or repo_path()
    payload = load_json(base / "config" / "dependency-graph.json", default={})
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    if isinstance(nodes, list) and isinstance(edges, list) and nodes and edges:
        descendants = {edge.get("to") for edge in edges if edge.get("from") == service_id}
        return len([item for item in descendants if isinstance(item, str)])

    fallbacks = overrides.get("downstream_count_fallbacks", {})
    if isinstance(fallbacks, dict):
        value = fallbacks.get(service_id)
        if isinstance(value, int):
            stale_reasons.append(f"dependency fanout for {service_id} used fallback override")
            return value

    stale_reasons.append(f"dependency fanout for {service_id} defaulted to 0")
    return 0


def receipt_matches_service(payload: dict[str, Any], service_id: str) -> bool:
    workflow_id = normalize_identifier(str(payload.get("workflow_id", "")))
    if service_id and service_id in workflow_id:
        return True
    summary = normalize_identifier(str(payload.get("summary", "")))
    if service_id and service_id in summary:
        return True
    for target in payload.get("targets", []):
        if not isinstance(target, dict):
            continue
        name = normalize_identifier(str(target.get("name", "")))
        if service_id and service_id in name:
            return True
        address = normalize_identifier(str(target.get("address", "")))
        if service_id and service_id in address:
            return True
    return False


def recent_failure_rate(
    workflow_id: str,
    service_id: str | None,
    lookback: int,
    repo_root: Path | None,
    overrides: dict[str, Any],
) -> float:
    base = repo_root or repo_path()
    override_map = overrides.get("recent_failure_rate_overrides", {})
    if service_id and isinstance(override_map, dict):
        override = override_map.get(service_id)
        if isinstance(override, (int, float)):
            return max(0.0, min(1.0, float(override)))

    receipts = sorted((base / "receipts" / "live-applies").glob("*.json"), reverse=True)[: max(lookback * 4, 20)]
    matched: list[bool] = []
    normalized_workflow = normalize_identifier(workflow_id)
    for receipt in receipts:
        try:
            payload = json.loads(receipt.read_text())
        except json.JSONDecodeError:
            continue
        candidate_workflow = normalize_identifier(str(payload.get("workflow_id", "")))
        if candidate_workflow == normalized_workflow or (service_id and receipt_matches_service(payload, service_id)):
            verification = payload.get("verification", [])
            failed = False
            if isinstance(verification, list):
                failed = any(
                    isinstance(item, dict) and str(item.get("result", "")).strip().lower() not in {"pass", "ok"}
                    for item in verification
                )
            matched.append(failed)
        if len(matched) >= lookback:
            break
    if not matched:
        return 0.0
    return sum(1 for failed in matched if failed) / len(matched)


def latest_mutation_age_hours(
    workflow_id: str,
    service_id: str | None,
    repo_root: Path | None,
    now: datetime,
    overrides: dict[str, Any],
) -> float | None:
    base = repo_root or repo_path()
    override_map = overrides.get("hours_since_last_mutation_overrides", {})
    if service_id and isinstance(override_map, dict):
        override = override_map.get(service_id)
        if isinstance(override, (int, float)):
            return float(override)

    normalized_workflow = normalize_identifier(workflow_id)
    for receipt in sorted((base / "receipts" / "live-applies").glob("*.json"), reverse=True):
        try:
            payload = json.loads(receipt.read_text())
        except json.JSONDecodeError:
            continue
        candidate_workflow = normalize_identifier(str(payload.get("workflow_id", "")))
        if candidate_workflow != normalized_workflow and not (
            service_id and receipt_matches_service(payload, service_id)
        ):
            continue
        for key in ("recorded_on", "applied_on"):
            raw = payload.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                if "T" in raw:
                    recorded = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                else:
                    recorded = datetime.fromisoformat(f"{raw}T00:00:00+00:00")
            except ValueError:
                continue
            if recorded.tzinfo is None:
                recorded = recorded.replace(tzinfo=UTC)
            return max(0.0, (now - recorded.astimezone(UTC)).total_seconds() / 3600)
    return None


def maintenance_window_active(service_id: str | None) -> bool:
    if not service_id:
        return False
    windows = list_active_windows_best_effort()
    for window in windows.values():
        candidate = window.get("service_id")
        if candidate in {service_id, "all"}:
            return True
    return False


def active_incident(service_id: str | None, overrides: dict[str, Any]) -> bool:
    if not service_id:
        return False
    incidents = overrides.get("active_incidents", [])
    return isinstance(incidents, list) and service_id in incidents


def compile_workflow_intent(
    workflow_id: str,
    arguments: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    workflows = workflow_catalog(repo_root)
    workflow = workflows.get(workflow_id)
    if not isinstance(workflow, dict):
        raise SystemExit(f"Unknown workflow '{workflow_id}'.")
    overrides = load_risk_scoring_overrides(repo_root)
    services = service_catalog(repo_root)
    owners = secret_owner_map(repo_root)
    service_id = infer_target_service_id(workflow_id, arguments, services, owners, overrides)
    target_vm = None
    if service_id and service_id in services:
        target_vm = services[service_id].get("vm")
    workflow_defaults = resolve_workflow_defaults(workflow_id, overrides)
    expected_change_count = workflow_defaults.get("expected_change_count")
    if not isinstance(expected_change_count, int):
        expected_change_count = int(
            load_risk_scoring_weights(repo_root).get("defaults", {}).get("expected_change_count", 5)
        )
    irreversible_count = int(workflow_defaults.get("irreversible_count", 0))
    unknown_count = int(workflow_defaults.get("unknown_count", 0))
    rollback_verified = bool(workflow_defaults.get("rollback_verified", False))
    live_impact = str(workflow.get("live_impact", "guest_live"))
    payload = {
        "intent_id": make_intent_id(workflow_id, arguments),
        "workflow_id": workflow_id,
        "workflow_description": str(workflow.get("description", "")),
        "arguments": arguments,
        "live_impact": live_impact,
        "target_service_id": service_id,
        "target_vm": target_vm,
        "rule_risk_class": resolve_rule_risk_class(live_impact),
        "rollback_verified": rollback_verified,
        "expected_change_count": expected_change_count,
        "irreversible_count": irreversible_count,
        "unknown_count": unknown_count,
    }
    lane_resolution = resolve_lanes(payload, repo_root=repo_root or repo_path())
    payload["required_lanes"] = list(lane_resolution.required_lanes)
    payload["resource_claims"] = [
        claim.as_dict() for claim in infer_resource_claims(payload, repo_root=repo_root or repo_path())
    ]
    semantic_diff = compute_semantic_diff(payload, repo_root=repo_root)
    if semantic_diff is not None:
        payload["semantic_diff"] = semantic_diff
        payload["expected_change_count"] = semantic_diff.total_changes
        payload["irreversible_count"] = semantic_diff.irreversible_count
        payload["unknown_count"] = semantic_diff.unknown_count
    return payload


def compute_semantic_diff(payload: dict[str, Any], *, repo_root: Path | None = None) -> Any | None:
    try:
        from platform.diff_engine import DiffEngine
    except Exception:
        return None
    try:
        return DiffEngine(repo_root=repo_root or repo_path()).compute(payload)
    except Exception:
        return None


def assemble_context(
    intent: ExecutionIntent | dict[str, Any],
    *,
    repo_root: Path | None = None,
    now: datetime | None = None,
) -> ScoringContext:
    if isinstance(intent, ExecutionIntent):
        payload = intent.as_dict()
    else:
        payload = intent
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    overrides = load_risk_scoring_overrides(repo_root)
    services = service_catalog(repo_root)
    weights = load_risk_scoring_weights(repo_root)
    defaults = weights.get("defaults", {})
    stale_reasons: list[str] = []

    target_service_id = payload.get("target_service_id")
    live_impact = str(payload.get("live_impact", "guest_live"))
    target_tier = resolve_target_tier(target_service_id, live_impact, services, overrides, stale_reasons)
    downstream_count = dependency_graph_descendants(target_service_id or "", repo_root, overrides, stale_reasons)
    lookback = int(defaults.get("failure_lookback", 10))
    failure_rate = recent_failure_rate(
        str(payload["workflow_id"]),
        target_service_id,
        lookback,
        repo_root,
        overrides,
    )
    expected_change_count = int(payload.get("expected_change_count", defaults.get("expected_change_count", 5)))
    if "expected_change_count" not in payload:
        stale_reasons.append("expected change count defaulted because diff engine is unavailable")
    irreversible_count = int(payload.get("irreversible_count", 0))
    unknown_count = int(payload.get("unknown_count", 0))
    rollback_verified = bool(payload.get("rollback_verified", False))
    in_window = maintenance_window_active(target_service_id)
    incident_open = active_incident(target_service_id, overrides)
    hours_since_last_mutation = latest_mutation_age_hours(
        str(payload["workflow_id"]),
        target_service_id,
        repo_root,
        current_time,
        overrides,
    )
    if hours_since_last_mutation is None:
        fallback = defaults.get("hours_since_last_mutation_if_unknown", 72)
        if isinstance(fallback, (int, float)):
            hours_since_last_mutation = float(fallback)
        stale_reasons.append("last mutation age defaulted because no matching receipt was found")

    signal_sources = {
        "target_tier": "config/risk-scoring-overrides.yaml"
        if target_service_id
        and isinstance(overrides.get("service_tiers"), dict)
        and target_service_id in overrides["service_tiers"]
        else "service-capability fallback",
        "downstream_count": "config/dependency-graph.json"
        if downstream_count and not any("fallback" in reason for reason in stale_reasons)
        else "config/risk-scoring-overrides.yaml",
        "failure_rate": "receipts/live-applies",
        "maintenance_window": "scripts/maintenance_window_tool.py",
        "recency": "receipts/live-applies",
    }

    return ScoringContext(
        workflow_id=str(payload["workflow_id"]),
        target_service_id=target_service_id,
        target_tier=target_tier,
        downstream_count=downstream_count,
        recent_failure_rate=failure_rate,
        expected_change_count=expected_change_count,
        irreversible_count=irreversible_count,
        unknown_count=unknown_count,
        rollback_verified=rollback_verified,
        in_maintenance_window=in_window,
        active_incident=incident_open,
        hours_since_last_mutation=hours_since_last_mutation,
        stale=bool(stale_reasons),
        stale_reasons=tuple(stale_reasons),
        signal_sources=signal_sources,
    )
