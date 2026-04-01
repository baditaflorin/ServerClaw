#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.ansible.vikunja import (
    VikunjaClient,
    VikunjaError,
    find_label_by_title,
    find_project_by_identifier,
    load_auth,
)


@dataclass(frozen=True)
class Action:
    kind: str
    action: str
    identifier: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "action": self.action,
            "id": self.identifier,
            "detail": self.detail,
        }


def load_desired_state(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Desired state must be a JSON object")
    projects = payload.get("projects", [])
    if not isinstance(projects, list):
        raise ValueError("Desired state must include a list-valued 'projects' key")
    return payload


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


def write_report(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ensure_labels(client: VikunjaClient, labels: list[dict[str, Any]], actions: list[Action]) -> dict[str, int]:
    existing = client.list_labels()
    label_ids: dict[str, int] = {}
    for label in labels:
        title = str(label.get("title", "")).strip()
        if not title:
            raise ValueError("Every label must define a non-empty title")
        existing_label = find_label_by_title(existing, title)
        if existing_label is None:
            created = client.create_label(
                {
                    "title": title,
                    "description": label.get("description", ""),
                    "hex_color": label.get("hex_color", ""),
                }
            )
            existing.append(created)
            existing_label = created
            actions.append(Action("label", "created", title, f"Created label '{title}'"))
        label_ids[title] = int(existing_label["id"])
    return label_ids


def resolve_user_id(client: VikunjaClient, username: str) -> int:
    results = client.search_users(username)
    for user in results:
        if user.get("username") == username:
            return int(user["id"])
    raise VikunjaError(f"Vikunja user '{username}' was not found")


def ensure_project(client: VikunjaClient, project_spec: dict[str, Any], actions: list[Action]) -> dict[str, Any]:
    existing = find_project_by_identifier(client.list_projects(), str(project_spec["identifier"]))
    payload = {
        "title": project_spec["title"],
        "description": project_spec.get("description", ""),
        "identifier": project_spec["identifier"],
        "hex_color": project_spec.get("hex_color", ""),
    }
    if existing is None:
        created = client.create_project(payload)
        actions.append(Action("project", "created", project_spec["identifier"], f"Created project '{project_spec['title']}'"))
        return created
    changed = False
    for key, value in payload.items():
        if existing.get(key) != value:
            changed = True
            break
    if changed:
        existing = client.update_project(int(existing["id"]), {**existing, **payload})
        actions.append(Action("project", "updated", project_spec["identifier"], f"Updated project '{project_spec['title']}'"))
    return existing


def ensure_project_members(client: VikunjaClient, project_id: int, members: list[dict[str, Any]], actions: list[Action]) -> None:
    current_members = client.list_project_users(project_id)
    by_username = {member.get("username"): member for member in current_members}
    for member in members:
        username = str(member["username"]).strip()
        permission = int(member.get("permission", 0))
        current = by_username.get(username)
        if current is None:
            client.add_project_user(project_id, username, permission)
            actions.append(Action("membership", "created", username, f"Added {username} to project {project_id}"))
            continue
        if int(current.get("permission", -1)) != permission:
            user_id = resolve_user_id(client, username)
            client.update_project_user(project_id, user_id, username, permission)
            actions.append(Action("membership", "updated", username, f"Updated {username} permission on project {project_id}"))


def ensure_project_webhooks(client: VikunjaClient, project_id: int, webhooks: list[dict[str, Any]], actions: list[Action]) -> None:
    current = client.list_webhooks(project_id)
    by_target = {webhook.get("target_url"): webhook for webhook in current}
    for webhook in webhooks:
        target_url = str(webhook["target_url"]).strip()
        existing = by_target.get(target_url)
        expected_events = sorted(str(event) for event in webhook.get("events", []))
        if existing is None:
            client.create_webhook(
                project_id,
                {
                    "target_url": target_url,
                    "secret": webhook.get("secret", ""),
                    "events": expected_events,
                },
            )
            actions.append(Action("webhook", "created", target_url, f"Created webhook for project {project_id}"))
            continue
        current_events = sorted(str(event) for event in existing.get("events", []))
        current_secret = str(existing.get("secret", ""))
        expected_secret = str(webhook.get("secret", ""))
        if current_events != expected_events or current_secret != expected_secret:
            client.delete_webhook(project_id, int(existing["id"]))
            client.create_webhook(
                project_id,
                {
                    "target_url": target_url,
                    "secret": expected_secret,
                    "events": expected_events,
                },
            )
            actions.append(Action("webhook", "updated", target_url, f"Recreated webhook for project {project_id}"))


def sync_state(*, auth_file: str, desired_state_file: str, summary_output: str | None = None) -> dict[str, Any]:
    desired_state = load_desired_state(Path(desired_state_file))
    client, auth = build_client(auth_file)
    actions: list[Action] = []
    project_summaries: list[dict[str, Any]] = []

    for project_spec in desired_state.get("projects", []):
        project = ensure_project(client, project_spec, actions)
        label_ids = ensure_labels(client, list(project_spec.get("labels", [])), actions)
        ensure_project_members(client, int(project["id"]), list(project_spec.get("members", [])), actions)
        ensure_project_webhooks(client, int(project["id"]), list(project_spec.get("webhooks", [])), actions)
        project_summaries.append(
            {
                "id": int(project["id"]),
                "identifier": project["identifier"],
                "title": project["title"],
                "labels": label_ids,
            }
        )

    summary = {
        "status": "ok",
        "base_url": auth["base_url"],
        "projects": project_summaries,
        "actions": [action.as_dict() for action in actions],
    }
    write_report(Path(summary_output) if summary_output else None, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize repo-managed Vikunja desired state.")
    parser.add_argument("--auth-file", required=True, help="Path to the Vikunja auth JSON file.")
    parser.add_argument("--desired-state-file", required=True, help="Path to the desired-state JSON file.")
    parser.add_argument("--summary-output", help="Optional JSON summary output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = sync_state(
        auth_file=args.auth_file,
        desired_state_file=args.desired_state_file,
        summary_output=args.summary_output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
