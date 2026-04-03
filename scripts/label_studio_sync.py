#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib import error, parse, request


def load_catalog(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text())
    projects = payload["projects"] if isinstance(payload, dict) else payload
    if not isinstance(projects, list):
        raise ValueError("project catalog must be a list or an object with a 'projects' list")

    normalized: list[dict[str, str]] = []
    for index, project in enumerate(projects):
        if not isinstance(project, dict):
            raise ValueError(f"project catalog entry {index} must be an object")
        for field in ("title", "description", "label_config"):
            value = project.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"project catalog entry {index} must define non-empty {field!r}")
        normalized.append(
            {
                "id": str(project.get("id") or project["title"]),
                "title": project["title"].strip(),
                "description": project["description"].strip(),
                "label_config": project["label_config"].strip(),
            }
        )
    return normalized


def request_json(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
    expected_status: tuple[int, ...] = (200,),
) -> Any:
    encoded = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Token {token}"
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=encoded, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            status = response.getcode()
            payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        status = exc.code
        payload = exc.read().decode("utf-8", errors="replace")
    if status not in expected_status:
        raise RuntimeError(f"{method} {url} returned {status}: {payload}")
    if not payload:
        return None
    return json.loads(payload)


def list_projects(base_url: str, token: str) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    page = 1
    while True:
      url = f"{base_url}/api/projects?{parse.urlencode({'page': page, 'page_size': 100})}"
      payload = request_json("GET", url, token)
      if isinstance(payload, dict) and "results" in payload:
          batch = payload.get("results", [])
          next_page = payload.get("next")
      elif isinstance(payload, list):
          batch = payload
          next_page = None
      else:
          raise RuntimeError(f"Unexpected project list payload: {payload!r}")
      projects.extend(batch)
      if not next_page or not batch:
          break
      page += 1
    return projects


def build_sync_plan(
    desired_projects: list[dict[str, str]],
    existing_projects: list[dict[str, Any]],
) -> dict[str, Any]:
    existing_by_title = {str(project.get("title", "")).strip(): project for project in existing_projects}
    creates: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    unchanged: list[str] = []

    for desired in desired_projects:
        existing = existing_by_title.get(desired["title"])
        if existing is None:
            creates.append(
                {
                    "id": desired["id"],
                    "title": desired["title"],
                    "payload": {
                        "title": desired["title"],
                        "description": desired["description"],
                        "label_config": desired["label_config"],
                    },
                }
            )
            continue

        changed_fields = {
            field: desired[field]
            for field in ("title", "description", "label_config")
            if str(existing.get(field, "")).strip() != desired[field]
        }
        if changed_fields:
            updates.append(
                {
                    "id": existing["id"],
                    "catalog_id": desired["id"],
                    "title": desired["title"],
                    "payload": changed_fields,
                }
            )
        else:
            unchanged.append(desired["id"])

    managed_titles = {project["title"] for project in desired_projects}
    unmanaged = sorted(
        str(project.get("title", "")).strip()
        for project in existing_projects
        if str(project.get("title", "")).strip() and str(project.get("title", "")).strip() not in managed_titles
    )
    return {
        "creates": creates,
        "updates": updates,
        "unchanged": unchanged,
        "unmanaged": unmanaged,
        "changed": bool(creates or updates),
    }


def verify_version(base_url: str) -> dict[str, Any]:
    payload = request_json("GET", f"{base_url}/api/version", "", expected_status=(200,))
    if not isinstance(payload, dict) or "release" not in payload:
        raise RuntimeError(f"Unexpected version payload: {payload!r}")
    return payload


def apply_sync_plan(base_url: str, token: str, plan: dict[str, Any]) -> dict[str, list[Any]]:
    created: list[Any] = []
    updated: list[Any] = []
    for item in plan["creates"]:
        created.append(request_json("POST", f"{base_url}/api/projects", token, item["payload"], expected_status=(201, 200)))
    for item in plan["updates"]:
        updated.append(
            request_json(
                "PATCH",
                f"{base_url}/api/projects/{item['id']}",
                token,
                item["payload"],
                expected_status=(200,),
            )
        )
    return {"created": created, "updated": updated}


def write_report(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.write_text(json.dumps(payload, indent=2) + "\n")


def build_report(
    mode: str,
    base_url: str,
    version: dict[str, Any],
    plan: dict[str, Any],
    applied: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    report = {
        "mode": mode,
        "base_url": base_url,
        "version": version,
        "changed": plan["changed"] if mode == "sync" else False,
        "creates": len(plan["creates"]),
        "updates": len(plan["updates"]),
        "unchanged": len(plan["unchanged"]),
        "unmanaged": plan["unmanaged"],
        "plan": plan,
    }
    if applied is not None:
        report["applied"] = {"created": len(applied["created"]), "updated": len(applied["updated"])}
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize repo-managed Label Studio projects.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_arguments(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--base-url", required=True)
        subparser.add_argument("--token-file", required=True)
        subparser.add_argument("--project-catalog", required=True)
        subparser.add_argument("--report-file")

    add_common_arguments(subparsers.add_parser("sync", help="Create or update managed projects."))
    add_common_arguments(subparsers.add_parser("verify", help="Fail if managed projects drift from repo truth."))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    token = Path(args.token_file).read_text().strip()
    if not token:
        raise ValueError("token file is empty")

    base_url = args.base_url.rstrip("/")
    catalog = load_catalog(Path(args.project_catalog))
    version = verify_version(base_url)
    existing = list_projects(base_url, token)
    plan = build_sync_plan(catalog, existing)
    report_path = Path(args.report_file) if args.report_file else None

    if args.command == "verify":
        report = build_report("verify", base_url, version, plan)
        write_report(report_path, report)
        print(json.dumps(report))
        if plan["changed"]:
            return 1
        return 0

    applied = apply_sync_plan(base_url, token, plan)
    report = build_report("sync", base_url, version, plan, applied=applied)
    write_report(report_path, report)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover - CLI error boundary
        print(json.dumps({"status": "error", "error": str(exc)}))
        raise
