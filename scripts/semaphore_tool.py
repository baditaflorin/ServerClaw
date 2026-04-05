#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, load_operator_auth
from platform.ansible.semaphore import SemaphoreClient, SemaphoreError


DEFAULT_AUTH_FILE = repo_path(".local", "semaphore", "admin-auth.json")


def build_client(auth_file: str) -> tuple[SemaphoreClient, dict]:
    auth = load_operator_auth(auth_file)
    client = SemaphoreClient(auth["base_url"], verify_ssl=bool(auth.get("verify_ssl", True)))
    api_token = auth.get("api_token", "").strip()
    if api_token and client.verify_api_token(api_token):
        client.set_api_token(api_token)
    else:
        client.login(auth["username"], auth["password"])
        api_token = client.create_api_token()
        auth["api_token"] = api_token
        Path(auth_file).expanduser().write_text(json.dumps(auth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        Path(auth_file).expanduser().chmod(0o600)
        client.set_api_token(api_token)
    return client, auth


def project_by_name(client: SemaphoreClient, project_name: str) -> dict:
    for project in client.list_projects():
        if project.get("name") == project_name:
            return project
    raise SemaphoreError(f"Semaphore project not found: {project_name}")


def template_by_name(client: SemaphoreClient, project_id: int, template_name: str) -> dict:
    for template in client.list_templates(project_id):
        if template.get("name") == template_name:
            return template
    raise SemaphoreError(f"Semaphore template not found: {template_name}")


def command_whoami(args) -> int:
    client, auth = build_client(args.auth_file)
    payload = client.get_user()
    payload["base_url"] = auth["base_url"]
    payload["project_name"] = auth.get("project_name")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_list_projects(args) -> int:
    client, _auth = build_client(args.auth_file)
    print(json.dumps(client.list_projects(), indent=2, sort_keys=True))
    return 0


def command_list_templates(args) -> int:
    client, auth = build_client(args.auth_file)
    project = project_by_name(client, args.project or auth.get("project_name", ""))
    print(json.dumps(client.list_templates(int(project["id"])), indent=2, sort_keys=True))
    return 0


def command_run_template(args) -> int:
    client, auth = build_client(args.auth_file)
    project = project_by_name(client, args.project or auth.get("project_name", ""))
    template = template_by_name(client, int(project["id"]), args.template)
    task = client.start_task(int(project["id"]), int(template["id"]), inventory_id=template.get("inventory_id"))
    if args.wait:
        task = client.wait_for_task(
            int(project["id"]),
            int(task["id"]),
            timeout_seconds=args.timeout,
            poll_seconds=args.poll_interval,
        )
    payload = {
        "project": project["name"],
        "project_id": int(project["id"]),
        "template": template["name"],
        "template_id": int(template["id"]),
        "task_id": int(task["id"]),
        "status": task.get("status"),
        "finished": task.get("status") not in {"waiting", "starting", "running", "stopping", "confirmed", "rejected", "waiting_confirmation"},
    }
    if args.wait:
        payload["raw_output"] = client.get_task_output(int(project["id"]), int(task["id"]))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if task.get("status") == "success" else 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_task_output(args) -> int:
    client, auth = build_client(args.auth_file)
    project = project_by_name(client, args.project or auth.get("project_name", ""))
    print(client.get_task_output(int(project["id"]), args.task_id), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed Semaphore API actions.")
    parser.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE), help="Path to the Semaphore auth JSON file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    whoami_parser = subparsers.add_parser("whoami", help="Show the configured Semaphore identity.")
    whoami_parser.set_defaults(func=command_whoami)

    list_projects = subparsers.add_parser("list-projects", help="List Semaphore projects.")
    list_projects.set_defaults(func=command_list_projects)

    list_templates = subparsers.add_parser("list-templates", help="List templates for one Semaphore project.")
    list_templates.add_argument("--project", help="Override project name from the auth file.")
    list_templates.set_defaults(func=command_list_templates)

    run_template = subparsers.add_parser("run-template", help="Run one template and optionally wait for completion.")
    run_template.add_argument("--project", help="Override project name from the auth file.")
    run_template.add_argument("--template", required=True, help="Template name to run.")
    run_template.add_argument("--wait", action="store_true", help="Wait for the task to finish.")
    run_template.add_argument("--timeout", type=int, default=300, help="Maximum wait time in seconds.")
    run_template.add_argument("--poll-interval", type=int, default=5, help="Polling interval in seconds.")
    run_template.set_defaults(func=command_run_template)

    task_output = subparsers.add_parser("task-output", help="Read raw output for one task id.")
    task_output.add_argument("--project", help="Override project name from the auth file.")
    task_output.add_argument("--task-id", required=True, type=int, help="Task id to inspect.")
    task_output.set_defaults(func=command_task_output)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, KeyError, SemaphoreError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("Semaphore", exc)


if __name__ == "__main__":
    raise SystemExit(main())
