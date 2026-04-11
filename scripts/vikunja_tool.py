#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import emit_cli_error
from platform.ansible.vikunja import (
    VikunjaClient,
    VikunjaError,
    create_api_token,
    load_auth,
    login,
    write_auth,
)


DEFAULT_AUTH_FILE = REPO_ROOT / ".local" / "vikunja" / "admin-auth.json"
DEFAULT_TOKEN_FILE = REPO_ROOT / ".local" / "vikunja" / "api-token.txt"


def read_text(path: str | Path) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8").strip()


def build_client(auth_file: str) -> tuple[VikunjaClient, dict[str, Any]]:
    auth = load_auth(auth_file)
    client = VikunjaClient(
        auth["base_url"],
        str(auth.get("api_token", "")).strip(),
        verify_ssl=bool(auth.get("verify_ssl", True)),
    )
    if not client.verify_api_token():
        raise VikunjaError(f"Vikunja API token in {auth_file} is invalid")
    return client, auth


def command_bootstrap(args: argparse.Namespace) -> int:
    password = read_text(args.password_file)
    session_token = login(args.base_url, args.username, password, verify_ssl=args.verify_ssl)
    created = create_api_token(
        args.base_url,
        session_token,
        title=args.token_title,
        expires_at=args.expires_at,
        verify_ssl=args.verify_ssl,
    )
    api_token = str(created.get("token", "")).strip()
    if not api_token:
        raise VikunjaError("Vikunja token bootstrap returned an empty API token")
    token_file = Path(args.token_file).expanduser()
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(api_token + "\n", encoding="utf-8")
    token_file.chmod(0o600)
    auth_payload = {
        "api_token": api_token,
        "base_url": args.base_url.rstrip("/"),
        "default_assignee_username": args.default_assignee,
        "project_identifier": args.project_identifier,
        "public_url": args.public_url.rstrip("/"),
        "username": args.username,
        "verify_ssl": args.verify_ssl,
    }
    write_auth(args.auth_file, auth_payload)
    print(json.dumps(auth_payload, indent=2, sort_keys=True))
    return 0


def command_whoami(args: argparse.Namespace) -> int:
    client, auth = build_client(args.auth_file)
    payload = client.whoami()
    payload["base_url"] = auth["base_url"]
    payload["project_identifier"] = auth.get("project_identifier")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_list_projects(args: argparse.Namespace) -> int:
    client, _auth = build_client(args.auth_file)
    print(json.dumps(client.list_projects(search=args.search or ""), indent=2, sort_keys=True))
    return 0


def command_list_tasks(args: argparse.Namespace) -> int:
    client, _auth = build_client(args.auth_file)
    print(json.dumps(client.list_tasks(search=args.search or ""), indent=2, sort_keys=True))
    return 0


def command_sync_state(args: argparse.Namespace) -> int:
    from vikunja_sync import sync_state

    summary = sync_state(
        auth_file=args.auth_file,
        desired_state_file=args.desired_state_file,
        summary_output=args.summary_output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed Vikunja API actions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Bootstrap a durable Vikunja API token from local auth.")
    bootstrap.add_argument("--base-url", required=True, help="Base URL for the Vikunja service, without /api/v1.")
    bootstrap.add_argument("--username", required=True, help="Local Vikunja username used during bootstrap.")
    bootstrap.add_argument("--password-file", required=True, help="Path to the local Vikunja bootstrap password file.")
    bootstrap.add_argument("--token-file", default=str(DEFAULT_TOKEN_FILE), help="Path to write the durable API token.")
    bootstrap.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE), help="Path to write the auth JSON file.")
    bootstrap.add_argument("--token-title", required=True, help="Human-readable API token title.")
    bootstrap.add_argument("--expires-at", required=True, help="ISO 8601 expiry timestamp for the durable API token.")
    bootstrap.add_argument("--public-url", required=True, help="Public browser URL for the Vikunja service.")
    bootstrap.add_argument("--project-identifier", required=True, help="Default repo-managed project identifier.")
    bootstrap.add_argument("--default-assignee", required=True, help="Default username used for alert-generated tasks.")
    bootstrap.add_argument("--verify-ssl", action=argparse.BooleanOptionalAction, default=True)
    bootstrap.set_defaults(func=command_bootstrap)

    parser.add_argument("--auth-file", default=str(DEFAULT_AUTH_FILE), help="Path to the Vikunja auth JSON file.")

    whoami = subparsers.add_parser("whoami", help="Show the configured Vikunja identity.")
    whoami.set_defaults(func=command_whoami)

    list_projects = subparsers.add_parser("list-projects", help="List Vikunja projects.")
    list_projects.add_argument("--search", help="Optional project search string.")
    list_projects.set_defaults(func=command_list_projects)

    list_tasks = subparsers.add_parser("list-tasks", help="List Vikunja tasks.")
    list_tasks.add_argument("--search", help="Optional task search string.")
    list_tasks.set_defaults(func=command_list_tasks)

    sync_state = subparsers.add_parser("sync-state", help="Synchronize the repo-managed Vikunja desired state.")
    sync_state.add_argument("--desired-state-file", required=True, help="Path to the desired-state JSON file.")
    sync_state.add_argument("--summary-output", help="Optional JSON summary output path.")
    sync_state.set_defaults(func=command_sync_state)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, KeyError, VikunjaError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("Vikunja", exc)


if __name__ == "__main__":
    raise SystemExit(main())
