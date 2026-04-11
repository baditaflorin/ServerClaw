#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.timeouts import timeout_limit, validate_timeout_hierarchy, load_hierarchy_payload


TIMEOUT_HIERARCHY_PATH = repo_path("config", "timeout-hierarchy.yaml")


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _validate_workflow_budgets() -> None:
    workflow_defaults = _require_mapping(
        load_yaml(repo_path("config", "workflow-defaults.yaml")), "workflow-defaults.yaml"
    )
    default_budget = _require_mapping(workflow_defaults.get("default_budget"), "workflow-defaults.yaml.default_budget")
    workflow_limit = timeout_limit("workflow_execution")
    default_timeout = default_budget.get("max_duration_seconds")
    if not isinstance(default_timeout, int) or default_timeout > workflow_limit:
        raise ValueError(
            f"config/workflow-defaults.yaml.default_budget.max_duration_seconds must be <= {workflow_limit}"
        )

    workflow_catalog = _require_mapping(
        load_json(repo_path("config", "workflow-catalog.json")), "workflow-catalog.json"
    )
    workflows = _require_mapping(workflow_catalog.get("workflows"), "workflow-catalog.json.workflows")
    for workflow_id, raw in workflows.items():
        if not isinstance(raw, dict):
            continue
        budget = raw.get("budget")
        if not isinstance(budget, dict):
            continue
        max_duration = budget.get("max_duration_seconds")
        if isinstance(max_duration, int) and max_duration > workflow_limit:
            raise ValueError(
                f"config/workflow-catalog.json.workflows.{workflow_id}.budget.max_duration_seconds "
                f"must be <= {workflow_limit}"
            )


def _validate_api_gateway_catalog() -> None:
    payload = _require_mapping(load_json(repo_path("config", "api-gateway-catalog.json")), "api-gateway-catalog.json")
    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError("api-gateway-catalog.json.services must be a list")
    http_limit = timeout_limit("http_request")
    for index, service in enumerate(services):
        if not isinstance(service, dict):
            continue
        timeout_seconds = service.get("timeout_seconds")
        if isinstance(timeout_seconds, int) and timeout_seconds > http_limit:
            raise ValueError(
                f"config/api-gateway-catalog.json.services[{index}].timeout_seconds must be <= {http_limit}"
            )


def _validate_health_probes() -> None:
    payload = _require_mapping(load_json(repo_path("config", "health-probe-catalog.json")), "health-probe-catalog.json")
    services = _require_mapping(payload.get("services"), "health-probe-catalog.json.services")
    readiness_limit = timeout_limit("health_probe")
    liveness_limit = timeout_limit("liveness_probe")
    for service_id, service in services.items():
        if not isinstance(service, dict):
            continue
        readiness = service.get("readiness")
        if isinstance(readiness, dict):
            timeout_seconds = readiness.get("timeout_seconds")
            if isinstance(timeout_seconds, int) and timeout_seconds > readiness_limit:
                raise ValueError(
                    f"health-probe-catalog.json.services.{service_id}.readiness.timeout_seconds "
                    f"must be <= {readiness_limit}"
                )
        liveness = service.get("liveness")
        if isinstance(liveness, dict):
            timeout_seconds = liveness.get("timeout_seconds")
            if isinstance(timeout_seconds, int) and timeout_seconds > liveness_limit:
                raise ValueError(
                    f"health-probe-catalog.json.services.{service_id}.liveness.timeout_seconds "
                    f"must be <= {liveness_limit}"
                )


def _validate_script_timeout_catalogs() -> None:
    manifest_paths = (
        repo_path("config", "diff-adapters.yaml"),
        repo_path("config", "check-runner-manifest.json"),
        repo_path("config", "validation-gate.json"),
        repo_path("config", "build-server.json"),
    )
    script_limit = timeout_limit("script_execution")
    for path in manifest_paths:
        if not path.exists():
            continue
        if path.suffix == ".yaml":
            payload = load_yaml(path)
        else:
            payload = load_json(path)
        serialized = json.dumps(payload)
        for marker in ("timeout_seconds", "default_timeout_seconds"):
            if marker not in serialized:
                continue
        if path.name == "diff-adapters.yaml":
            adapters = payload.get("adapters", [])
            for index, adapter in enumerate(adapters):
                if not isinstance(adapter, dict):
                    continue
                timeout_seconds = adapter.get("timeout_seconds")
                if isinstance(timeout_seconds, int) and timeout_seconds > script_limit:
                    raise ValueError(f"{path.name}.adapters[{index}].timeout_seconds must be <= {script_limit}")
        elif path.name in {"check-runner-manifest.json", "validation-gate.json"}:
            checks = payload.get("checks", [])
            for index, check in enumerate(checks):
                if not isinstance(check, dict):
                    continue
                timeout_seconds = check.get("timeout_seconds")
                if isinstance(timeout_seconds, int) and timeout_seconds > script_limit:
                    raise ValueError(f"{path.name}.checks[{index}].timeout_seconds must be <= {script_limit}")
        elif path.name == "build-server.json":
            timeout_seconds = payload.get("default_timeout_seconds")
            if isinstance(timeout_seconds, int) and timeout_seconds > script_limit:
                raise ValueError(f"{path.name}.default_timeout_seconds must be <= {script_limit}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the platform timeout hierarchy and its bound config surfaces."
    )
    parser.add_argument("path", nargs="?", default=str(TIMEOUT_HIERARCHY_PATH))
    args = parser.parse_args()

    try:
        payload = load_hierarchy_payload(args.path)
        validate_timeout_hierarchy(payload, path=str(Path(args.path)))
        _validate_workflow_budgets()
        _validate_api_gateway_catalog()
        _validate_health_probes()
        _validate_script_timeout_catalogs()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("Timeout hierarchy", exc)

    print(f"Timeout hierarchy OK: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
