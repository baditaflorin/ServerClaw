from __future__ import annotations

from pathlib import Path
from typing import Any

from .repo import REPO_ROOT, load_json, repo_path


WORKFLOW_CATALOG_PATH = repo_path("config", "workflow-catalog.json")
COMMAND_CATALOG_PATH = repo_path("config", "command-catalog.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
SECRET_MANIFEST_PATH = repo_path("config", "controller-local-secrets.json")


def _repo_catalog_path(repo_root: Path | None, *parts: str) -> Path:
    base = REPO_ROOT if repo_root is None else Path(repo_root)
    return base.joinpath(*parts)


def load_workflow_catalog(path: Path | None = None, *, repo_root: Path | None = None) -> dict[str, Any]:
    payload = load_json(path or _repo_catalog_path(repo_root, "config", "workflow-catalog.json"))
    if not isinstance(payload, dict):
        raise ValueError("config/workflow-catalog.json must define an object")
    return payload


def workflow_entries(repo_root: Path | None = None) -> dict[str, dict[str, Any]]:
    payload = load_workflow_catalog(repo_root=repo_root)
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError("config/workflow-catalog.json must define a workflows object")
    return {
        workflow_id: workflow
        for workflow_id, workflow in workflows.items()
        if isinstance(workflow_id, str) and isinstance(workflow, dict)
    }


def load_command_catalog(path: Path | None = None, *, repo_root: Path | None = None) -> dict[str, Any]:
    payload = load_json(path or _repo_catalog_path(repo_root, "config", "command-catalog.json"))
    if not isinstance(payload, dict):
        raise ValueError("config/command-catalog.json must define an object")
    return payload


def load_service_catalog(path: Path | None = None, *, repo_root: Path | None = None) -> dict[str, Any]:
    payload = load_json(path or _repo_catalog_path(repo_root, "config", "service-capability-catalog.json"))
    if not isinstance(payload, dict):
        raise ValueError("config/service-capability-catalog.json must define an object")
    return payload


def service_entries(repo_root: Path | None = None) -> dict[str, dict[str, Any]]:
    payload = load_service_catalog(repo_root=repo_root)
    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError("config/service-capability-catalog.json must define a services list")
    result: dict[str, dict[str, Any]] = {}
    for service in services:
        if not isinstance(service, dict):
            continue
        service_id = service.get("id")
        if isinstance(service_id, str) and service_id.strip():
            result[service_id] = service
    return result


def load_secret_manifest(path: Path | None = None, *, repo_root: Path | None = None) -> dict[str, Any]:
    payload = load_json(path or _repo_catalog_path(repo_root, "config", "controller-local-secrets.json"))
    if not isinstance(payload, dict):
        raise ValueError("config/controller-local-secrets.json must define an object")
    return payload
