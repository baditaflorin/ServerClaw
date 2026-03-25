from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTION_LANES_PATH = REPO_ROOT / "config" / "execution-lanes.yaml"
DEPENDENCY_GRAPH_PATH = REPO_ROOT / "config" / "dependency-graph.json"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
ALLOWED_SERIALISATION = {"strict", "resource_lock"}


@dataclass(frozen=True)
class ExecutionLaneDefinition:
    lane_id: str
    hostname: str | None
    vmid: int | None
    services: tuple[str, ...]
    max_concurrent_ops: int
    serialisation: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionLaneCatalog:
    schema_version: str
    lanes: dict[str, ExecutionLaneDefinition]
    service_to_lane: dict[str, str]
    host_to_lane: dict[str, str]


@dataclass(frozen=True)
class LaneResolution:
    primary_lane_id: str | None
    required_lanes: tuple[str, ...]
    dependency_lanes: tuple[str, ...]
    resolution_source: str


def _yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _json_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, path)


def _require_optional_int(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer or null")
    return value


def _require_string_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    items: list[str] = []
    for index, item in enumerate(value):
        items.append(_require_string(item, f"{path}[{index}]"))
    return items


def load_execution_lane_catalog(
    *,
    repo_root: Path | None = None,
    path: Path | None = None,
) -> ExecutionLaneCatalog:
    root = repo_root or REPO_ROOT
    catalog_path = path or (root / "config" / "execution-lanes.yaml")
    if not catalog_path.exists():
        return ExecutionLaneCatalog(
            schema_version="missing",
            lanes={},
            service_to_lane={},
            host_to_lane={},
        )

    payload = _yaml_mapping(catalog_path)
    schema_version = _require_string(payload.get("schema_version"), f"{catalog_path}.schema_version")
    lanes_payload = payload.get("lanes")

    lanes: dict[str, ExecutionLaneDefinition] = {}
    service_to_lane: dict[str, str] = {}
    host_to_lane: dict[str, str] = {}

    lane_entries: list[tuple[str, dict[str, Any], str]]
    if isinstance(lanes_payload, dict):
        lane_entries = []
        for lane_id, raw_lane in lanes_payload.items():
            normalized_lane_id = _require_string(lane_id, f"{catalog_path}.lanes key")
            lane_entries.append(
                (
                    normalized_lane_id,
                    _require_mapping(raw_lane, f"{catalog_path}.lanes.{normalized_lane_id}"),
                    f"{catalog_path}.lanes.{normalized_lane_id}",
                )
            )
    else:
        raw_lanes = _require_list(lanes_payload, f"{catalog_path}.lanes")
        lane_entries = []
        for index, raw_lane in enumerate(raw_lanes):
            lane = _require_mapping(raw_lane, f"{catalog_path}.lanes[{index}]")
            normalized_lane_id = _require_string(lane.get("lane_id"), f"{catalog_path}.lanes[{index}].lane_id")
            lane_entries.append((normalized_lane_id, lane, f"{catalog_path}.lanes[{index}]"))

    for normalized_lane_id, lane, lane_path in lane_entries:
        hostname = _require_optional_string(
            lane.get("hostname"),
            f"{lane_path}.hostname",
        )
        vmid = _require_optional_int(lane.get("vmid", lane.get("vm_id")), f"{lane_path}.vm_id")
        services = tuple(
            service.replace("-", "_")
            for service in _require_string_list(
                lane.get("services"),
                f"{lane_path}.services",
            )
        )
        max_concurrent_ops = _require_optional_int(
            lane.get("max_concurrent_ops"),
            f"{lane_path}.max_concurrent_ops",
        )
        if max_concurrent_ops is None or max_concurrent_ops < 1:
            raise ValueError(f"{lane_path}.max_concurrent_ops must be >= 1")
        serialisation = _require_string(
            lane.get("serialisation"),
            f"{lane_path}.serialisation",
        )
        if serialisation not in ALLOWED_SERIALISATION:
            raise ValueError(f"{lane_path}.serialisation must be one of {sorted(ALLOWED_SERIALISATION)}")
        aliases = tuple(
            _require_string(alias, f"{lane_path}.aliases[{index}]")
            for index, alias in enumerate(_require_string_list(
                lane.get("aliases"),
                f"{lane_path}.aliases",
            ))
        )
        definition = ExecutionLaneDefinition(
            lane_id=normalized_lane_id,
            hostname=hostname,
            vmid=vmid,
            services=services,
            max_concurrent_ops=max_concurrent_ops,
            serialisation=serialisation,
            aliases=aliases,
        )
        lanes[normalized_lane_id] = definition
        for service in services:
            if service in service_to_lane:
                raise ValueError(f"service '{service}' is assigned to multiple execution lanes")
            service_to_lane[service] = normalized_lane_id
        for candidate in [hostname, *aliases]:
            if candidate is None:
                continue
            if candidate in host_to_lane:
                raise ValueError(f"host '{candidate}' is assigned to multiple execution lanes")
            host_to_lane[candidate] = normalized_lane_id

    return ExecutionLaneCatalog(
        schema_version=schema_version,
        lanes=lanes,
        service_to_lane=service_to_lane,
        host_to_lane=host_to_lane,
    )


def _workflow_lane_override(workflow_id: str, *, repo_root: Path) -> list[str]:
    path = repo_root / "config" / "workflow-catalog.json"
    if not path.exists():
        return []
    payload = _json_mapping(path)
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        return []
    workflow = workflows.get(workflow_id)
    if not isinstance(workflow, dict):
        return []
    explicit = workflow.get("execution_lane_id")
    if isinstance(explicit, str) and explicit.strip():
        return [explicit.strip()]
    lanes = workflow.get("required_lanes")
    if not isinstance(lanes, list):
        return []
    return [str(item).strip() for item in lanes if isinstance(item, str) and str(item).strip()]


def _dependency_lane_ids(service_ids: set[str], catalog: ExecutionLaneCatalog, *, repo_root: Path) -> list[str]:
    path = repo_root / "config" / "dependency-graph.json"
    if not path.exists():
        return []
    payload = _json_mapping(path)
    edges = payload.get("edges")
    if not isinstance(edges, list):
        return []
    dependencies: list[str] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from", "")).strip().replace("-", "_")
        target = str(edge.get("to", "")).strip().replace("-", "_")
        if source not in service_ids or not target:
            continue
        lane_id = catalog.service_to_lane.get(target)
        if lane_id:
            dependencies.append(lane_id)
    return dependencies


def _intent_payload(intent: Any) -> dict[str, Any]:
    if hasattr(intent, "as_dict"):
        payload = intent.as_dict()
        if isinstance(payload, dict):
            return payload
    if isinstance(intent, dict):
        return dict(intent)
    payload: dict[str, Any] = {}
    for field in (
        "workflow_id",
        "target_service_id",
        "target_vm",
        "arguments",
        "required_read_surfaces",
        "required_lanes",
        "target",
        "scope",
    ):
        if hasattr(intent, field):
            payload[field] = getattr(intent, field)
    return payload


def resolve_lanes(intent: Any, *, repo_root: Path | None = None) -> LaneResolution:
    root = repo_root or REPO_ROOT
    catalog = load_execution_lane_catalog(repo_root=root)
    if not catalog.lanes:
        return LaneResolution(primary_lane_id=None, required_lanes=(), dependency_lanes=(), resolution_source="none")

    payload = _intent_payload(intent)
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}

    workflow_id = str(payload.get("workflow_id", "")).strip()
    service_ids: set[str] = set()
    target_service = payload.get("target_service_id")
    if isinstance(target_service, str) and target_service.strip():
        service_ids.add(target_service.strip().replace("-", "_"))
    target_block = payload.get("target")
    if isinstance(target_block, dict):
        for service_id in target_block.get("services", []):
            if isinstance(service_id, str) and service_id.strip():
                service_ids.add(service_id.strip().replace("-", "_"))
    for key in ("service", "service_id", "target_service"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            service_ids.add(value.strip().replace("-", "_"))

    primary_candidates: list[str] = []
    resolution_source = "none"
    for service_id in sorted(service_ids):
        lane_id = catalog.service_to_lane.get(service_id)
        if lane_id and lane_id not in primary_candidates:
            primary_candidates.append(lane_id)
            resolution_source = "service_catalog"

    host_candidates: list[str] = []
    for value in (
        payload.get("target_vm"),
        arguments.get("target_vm"),
        arguments.get("host"),
        arguments.get("target"),
    ):
        if isinstance(value, str) and value.strip():
            host_candidates.append(value.strip())
    scope_block = payload.get("scope")
    if isinstance(scope_block, dict):
        for host in scope_block.get("allowed_hosts", []):
            if isinstance(host, str) and host.strip():
                host_candidates.append(host.strip())

    for host in host_candidates:
        lane_id = catalog.host_to_lane.get(host)
        if lane_id and lane_id not in primary_candidates:
            primary_candidates.append(lane_id)
            if resolution_source == "none":
                resolution_source = "host_target"

    workflow_lane_override = _workflow_lane_override(workflow_id, repo_root=root)
    for lane_id in workflow_lane_override:
        if lane_id in catalog.lanes and lane_id not in primary_candidates:
            primary_candidates.append(lane_id)
            if resolution_source == "none":
                resolution_source = "workflow_catalog"

    dependency_lanes = [
        lane_id
        for lane_id in _dependency_lane_ids(service_ids, catalog, repo_root=root)
        if lane_id not in primary_candidates
    ]

    if not primary_candidates:
        return LaneResolution(
            primary_lane_id=None,
            required_lanes=tuple(dict.fromkeys(dependency_lanes)),
            dependency_lanes=tuple(dict.fromkeys(dependency_lanes)),
            resolution_source=resolution_source,
        )

    primary_lane_id = primary_candidates[0]
    if len(primary_candidates) > 1 and "lane:platform" in catalog.lanes:
        primary_lane_id = "lane:platform"

    required_lanes: list[str] = [primary_lane_id]
    for lane_id in [*primary_candidates, *dependency_lanes]:
        if lane_id != primary_lane_id and lane_id not in required_lanes:
            required_lanes.append(lane_id)

    dependency_lane_ids = [lane_id for lane_id in dependency_lanes if lane_id != primary_lane_id]
    return LaneResolution(
        primary_lane_id=primary_lane_id,
        required_lanes=tuple(required_lanes),
        dependency_lanes=tuple(dict.fromkeys(dependency_lane_ids)),
        resolution_source=resolution_source,
    )
