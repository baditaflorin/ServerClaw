#!/usr/bin/env python3
"""Windmill wrapper for turning Alertmanager payloads into Vikunja tasks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _repo_paths(repo_root: Path) -> tuple[Path, Path]:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root / "platform" / "ansible" / "vikunja.py", repo_root / ".local" / "vikunja" / "admin-auth.json"


def _load_module(path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("lv3_vikunja_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _marker(fingerprint: str) -> str:
    return f"alert-fingerprint:{fingerprint}"


def _task_title(alert: dict[str, Any]) -> str:
    labels = alert.get("labels", {})
    severity = labels.get("severity", "unknown")
    alert_name = labels.get("alertname", "unnamed-alert")
    instance = labels.get("instance", labels.get("service", "unknown-instance"))
    return f"[{severity}] {alert_name} on {instance}"


def _task_description(alert: dict[str, Any], marker: str) -> str:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    lines = [
        f"Alert fingerprint: `{marker}`",
        "",
        f"- Status: `{alert.get('status', 'unknown')}`",
        f"- Service: `{labels.get('service', 'unknown')}`",
        f"- Alert: `{labels.get('alertname', 'unnamed-alert')}`",
        f"- Severity: `{labels.get('severity', 'unknown')}`",
        f"- Instance: `{labels.get('instance', 'unknown')}`",
    ]
    if annotations.get("summary"):
        lines.append(f"- Summary: {annotations['summary']}")
    if annotations.get("description"):
        lines.append("")
        lines.append(annotations["description"])
    return "\n".join(lines)


def _ensure_task_for_alert(module, client, auth: dict[str, Any], alert: dict[str, Any]) -> dict[str, Any]:
    marker = _marker(str(alert.get("fingerprint", "")).strip())
    if marker == "alert-fingerprint:":
        raise RuntimeError("alert fingerprint is required")
    project_identifier = auth.get("project_identifier", "PLATOPS")
    projects = client.list_projects()
    project = module.find_project_by_identifier(projects, project_identifier)
    if project is None:
        raise RuntimeError(f"project '{project_identifier}' is missing in Vikunja")
    tasks = client.list_tasks(search=marker, project_id=int(project["id"]))
    if tasks:
        return tasks[0]
    labels = client.list_labels(search="incident")
    label = next((entry for entry in labels if entry.get("title") == "incident"), None)
    if label is None:
        label = client.create_label({"title": "incident", "description": "Incident response work item", "hex_color": "#862e9c"})
    assignee_username = auth.get("default_assignee_username", "")
    assignee_ids = []
    if assignee_username:
        assignee_ids = [int(user["id"]) for user in client.search_users(assignee_username) if user.get("username") == assignee_username]
    created = client.create_task(
        int(project["id"]),
        {
            "title": _task_title(alert),
            "description": _task_description(alert, marker),
            "project_id": int(project["id"]),
        },
    )
    client.replace_task_labels(int(created["id"]), [int(label["id"])])
    if assignee_ids:
        client.replace_task_assignees(int(created["id"]), assignee_ids)
    return client.get_task(int(created["id"]))


def _resolve_task_for_alert(client, alert: dict[str, Any]) -> dict[str, Any] | None:
    marker = _marker(str(alert.get("fingerprint", "")).strip())
    tasks = client.list_tasks(search=marker)
    if not tasks:
        return None
    task = client.get_task(int(tasks[0]["id"]))
    if task.get("done"):
        return task
    updated = {**task, "done": True}
    resolved = client.update_task(int(task["id"]), updated)
    client.add_comment(int(task["id"]), f"Resolved at {alert.get('endsAt') or alert.get('updatedAt') or 'unknown'}")
    return resolved


def main(alert_payload: dict[str, Any] | None = None, repo_path: str = "/srv/proxmox_florin_server") -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    payload = alert_payload or {}
    if not isinstance(payload, dict):
        return {"status": "blocked", "reason": "alert_payload must be an object"}

    module_path, auth_path = _repo_paths(repo_root)
    if not module_path.exists():
        return {"status": "blocked", "reason": "platform Vikunja helper is missing from the worker checkout"}
    if not auth_path.exists():
        return {"status": "blocked", "reason": "Vikunja auth file is missing from the worker checkout"}

    module = _load_module(module_path)
    auth = module.load_auth(auth_path)
    client = module.VikunjaClient(auth["base_url"], auth["api_token"], verify_ssl=bool(auth.get("verify_ssl", True)))
    if not client.verify_api_token():
        return {"status": "error", "reason": "Vikunja API token is invalid"}

    status = str(payload.get("status", "")).lower()
    alerts = payload.get("alerts", [])
    if not isinstance(alerts, list) or not alerts:
        return {"status": "blocked", "reason": "alert_payload.alerts must be a non-empty list"}

    handled: list[dict[str, Any]] = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        severity = str(alert.get("labels", {}).get("severity", "")).lower()
        if severity not in {"warning", "critical"}:
            continue
        if status == "resolved":
            task = _resolve_task_for_alert(client, alert)
            handled.append(
                {
                    "fingerprint": alert.get("fingerprint"),
                    "action": "resolved",
                    "task_id": task.get("id") if task else None,
                }
            )
        else:
            task = _ensure_task_for_alert(module, client, auth, alert)
            handled.append(
                {
                    "fingerprint": alert.get("fingerprint"),
                    "action": "upserted",
                    "task_id": task.get("id"),
                    "task_identifier": task.get("identifier"),
                }
            )

    return {
        "status": "ok",
        "handled": handled,
        "alert_count": len(alerts),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ADR 0286 alert-to-task Windmill wrapper.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--payload-file", type=Path, help="Optional JSON Alertmanager payload file.")
    args = parser.parse_args()
    payload = json.loads(args.payload_file.read_text(encoding="utf-8")) if args.payload_file else None
    print(json.dumps(main(alert_payload=payload, repo_path=args.repo_path), indent=2, sort_keys=True))
