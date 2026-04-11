#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import emit_cli_error, load_operator_auth
from platform.ansible.plane import PlaneClient, PlaneError, PlaneSessionClient, bootstrap_plane


DEFAULT_AUTH_FILE = REPO_ROOT / ".local" / "plane" / "admin-auth.json"


def build_client(auth_file: str) -> tuple[PlaneClient, dict]:
    auth = load_operator_auth(auth_file)
    api_token = str(auth.get("api_token", "")).strip()
    client = PlaneClient(auth["base_url"], api_token, verify_ssl=bool(auth.get("verify_ssl", True)))
    if client.verify_api_key():
        return client, auth
    summary = bootstrap_plane(
        base_url=auth["base_url"],
        admin_email=auth["email"],
        admin_password=auth["password"],
        spec={
            "admin": {
                "email": auth["email"],
                "first_name": auth.get("first_name", "LV3"),
                "last_name": auth.get("last_name", "Operator"),
                "company_name": auth.get("company_name", "LV3"),
                "is_telemetry_enabled": False,
            },
            "workspace": {
                "name": auth["workspace_name"],
                "slug": auth["workspace_slug"],
            },
            "project": {
                "name": auth["project_name"],
                "identifier": auth["project_identifier"],
            },
            "api_token": {
                "label": "LV3 Plane Automation",
                "description": "Repo-managed Plane automation token.",
            },
        },
        verify_ssl=bool(auth.get("verify_ssl", True)),
        existing_api_token=api_token,
    )
    auth["api_token"] = summary["api_token"]
    Path(auth_file).expanduser().write_text(json.dumps(auth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(auth_file).expanduser().chmod(0o600)
    client = PlaneClient(auth["base_url"], auth["api_token"], verify_ssl=bool(auth.get("verify_ssl", True)))
    return client, auth


def command_whoami(args) -> int:
    client, auth = build_client(args.auth_file)
    payload = client.whoami()
    payload["base_url"] = auth["base_url"]
    payload["workspace_slug"] = auth.get("workspace_slug")
    payload["project_identifier"] = auth.get("project_identifier")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_list_workspaces(args) -> int:
    auth = load_auth(args.auth_file)
    session = PlaneSessionClient(auth["base_url"], verify_ssl=bool(auth.get("verify_ssl", True)))
    sign_in_error = session.sign_in_admin(auth["email"], auth["password"])
    if sign_in_error:
        raise PlaneError(f"Plane admin sign-in failed with error_code={sign_in_error}")
    print(json.dumps(session.list_workspaces(), indent=2, sort_keys=True))
    return 0


def command_list_projects(args) -> int:
    client, auth = build_client(args.auth_file)
    workspace = args.workspace or auth.get("workspace_slug", "")
    print(json.dumps(client.list_projects(workspace), indent=2, sort_keys=True))
    return 0


def _project_for_identifier(client: PlaneClient, workspace_slug: str, identifier: str) -> dict:
    for project in client.list_projects(workspace_slug):
        if project.get("identifier") == identifier or project.get("name") == identifier:
            return project
    raise PlaneError(f"Plane project not found: {identifier}")


def command_list_issues(args) -> int:
    client, auth = build_client(args.auth_file)
    workspace = args.workspace or auth.get("workspace_slug", "")
    project = _project_for_identifier(client, workspace, args.project or auth.get("project_identifier", ""))
    print(json.dumps(client.list_issues(workspace, project["id"]), indent=2, sort_keys=True))
    return 0


def command_create_issue(args) -> int:
    client, auth = build_client(args.auth_file)
    workspace = args.workspace or auth.get("workspace_slug", "")
    project = _project_for_identifier(client, workspace, args.project or auth.get("project_identifier", ""))
    states = {state.get("name"): state.get("id") for state in client.list_states(workspace, project["id"])}
    payload = {"name": args.name}
    if args.description:
        payload["description_html"] = f"<p>{html.escape(args.description)}</p>"
    if args.external_id:
        payload["external_id"] = args.external_id
        payload["external_source"] = args.external_source
    if args.state and args.state in states:
        payload["state_id"] = states[args.state]
    created = client.create_issue(workspace, project["id"], payload)
    print(json.dumps(created, indent=2, sort_keys=True))
    return 0


def command_sync_adrs(args) -> int:
    from sync_adrs_to_plane import sync_adrs

    summary = sync_adrs(
        auth_file=args.auth_file,
        adr_dir=args.adr_dir,
        adr_ids=args.adr,
        summary_output=args.summary_output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed Plane API actions.")
    parser.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE), help="Path to the Plane auth JSON file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    whoami_parser = subparsers.add_parser("whoami", help="Show the configured Plane identity.")
    whoami_parser.set_defaults(func=command_whoami)

    list_workspaces = subparsers.add_parser("list-workspaces", help="List Plane workspaces.")
    list_workspaces.set_defaults(func=command_list_workspaces)

    list_projects = subparsers.add_parser("list-projects", help="List Plane projects for one workspace.")
    list_projects.add_argument("--workspace", help="Workspace slug.")
    list_projects.set_defaults(func=command_list_projects)

    list_issues = subparsers.add_parser("list-issues", help="List Plane issues for one project.")
    list_issues.add_argument("--workspace", help="Workspace slug.")
    list_issues.add_argument("--project", help="Project identifier or name.")
    list_issues.set_defaults(func=command_list_issues)

    create_issue = subparsers.add_parser("create-issue", help="Create one Plane issue.")
    create_issue.add_argument("--workspace", help="Workspace slug.")
    create_issue.add_argument("--project", help="Project identifier or name.")
    create_issue.add_argument("--name", required=True, help="Issue title.")
    create_issue.add_argument("--description", help="Plain-text issue description.")
    create_issue.add_argument("--state", help="Optional state name.")
    create_issue.add_argument("--external-id", help="Optional external identifier.")
    create_issue.add_argument(
        "--external-source", default="repo_manual", help="External source when external-id is set."
    )
    create_issue.set_defaults(func=command_create_issue)

    sync_adrs = subparsers.add_parser("sync-adrs", help="Synchronize ADR markdown into Plane issues.")
    sync_adrs.add_argument("--adr-dir", default=str(REPO_ROOT / "docs" / "adr"), help="ADR directory to scan.")
    sync_adrs.add_argument("--adr", action="append", help="Optional ADR id to sync. Repeat for multiple ids.")
    sync_adrs.add_argument("--summary-output", help="Optional JSON summary output path.")
    sync_adrs.set_defaults(func=command_sync_adrs)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, KeyError, PlaneError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("Plane", exc)


if __name__ == "__main__":
    raise SystemExit(main())
