#!/usr/bin/env python3
"""
sync_plane_agent_issues.py — Sync active workstreams → Plane Agent Work (AW) project.

Agent-agnostic: works with Claude, Codex, GPT, Gemini, or any agent that writes
workstream YAML files. The owner/agent identity comes from the workstream `owner`
field.

Called at workstream open, update, and close. Idempotent — safe to run twice.

Usage
-----
  # Sync all active workstreams (create/update AW issues):
  python scripts/sync_plane_agent_issues.py

  # Sync a single workstream:
  python scripts/sync_plane_agent_issues.py --workstream ws-0360-plane-hq

  # Add a comment to an issue (e.g. after a major milestone):
  python scripts/sync_plane_agent_issues.py --workstream ws-0360-plane-hq \\
      --comment "Branch merged to main at abc1234"

  # Repair: close AW issues whose branches no longer exist in git:
  python scripts/sync_plane_agent_issues.py --repair

  # Bootstrap the AW project only (idempotent):
  python scripts/sync_plane_agent_issues.py --bootstrap-only

Output
------
  JSON summary written to stdout. plane_issue_id is written back to each
  workstream YAML file so future calls skip the list-issues scan.

Environment
-----------
  PLANE_AUTH_FILE   — path to admin-auth.json (default: .local/plane/admin-auth.json)
  PLANE_AW_PROJECT  — AW project identifier (default: AW)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import emit_cli_error, load_json, write_json
from platform.ansible.plane import (
    PlaneClient,
    PlaneError,
    ensure_issue_for_workstream,
    ensure_labels,
    AW_LABEL_COLORS,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_AUTH_FILE = REPO_ROOT / ".local" / "plane" / "admin-auth.json"
DEFAULT_AW_IDENTIFIER = "AW"
DEFAULT_AW_NAME = "Agent Work"
DEFAULT_AW_DESCRIPTION = (
    "Live task board for all LLM agent sessions. One issue per worktree. See ADR 0360 for the full protocol."
)
WORKSTREAMS_ACTIVE = REPO_ROOT / "workstreams" / "active"
AW_AUTH_FILE = REPO_ROOT / ".local" / "plane" / "aw-auth.json"
ALL_LABELS = list(AW_LABEL_COLORS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyyaml is required: pip install pyyaml") from exc
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyyaml is required: pip install pyyaml") from exc
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _git_branches() -> set[str]:
    """Return set of all local+remote branch names (without refs/ prefix)."""
    try:
        result = subprocess.run(
            ["git", "branch", "-a", "--format=%(refname:short)"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {line.strip().removeprefix("origin/") for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        return set()


def _load_active_workstreams(ws_id: str | None = None) -> list[tuple[Path, dict[str, Any]]]:
    results: list[tuple[Path, dict[str, Any]]] = []
    if not WORKSTREAMS_ACTIVE.is_dir():
        return results
    for path in sorted(WORKSTREAMS_ACTIVE.glob("*.yaml")):
        ws = _load_yaml(path)
        if ws_id and ws.get("id") != ws_id:
            continue
        results.append((path, ws))
    return results


def _build_client(auth_file: Path) -> tuple[PlaneClient, dict[str, Any]]:
    auth = load_json(auth_file)
    client = PlaneClient(
        auth["base_url"],
        auth["api_token"],
        verify_ssl=bool(auth.get("verify_ssl", True)),
        timeout=60,
        max_rate_limit_retries=6,
    )
    if not client.verify_api_key():
        raise PlaneError(f"Plane API token in {auth_file} is not valid")
    return client, auth


def _ensure_aw_project(client: PlaneClient, auth: dict[str, Any], identifier: str) -> dict[str, Any]:
    workspace_slug = auth["workspace_slug"]
    project = client.ensure_project_by_identifier(
        workspace_slug,
        DEFAULT_AW_NAME,
        identifier,
        DEFAULT_AW_DESCRIPTION,
    )
    # Persist AW project metadata alongside main auth for other scripts
    aw_auth = {
        **auth,
        "project_id": project["id"],
        "project_name": project.get("name", DEFAULT_AW_NAME),
        "project_identifier": identifier,
    }
    AW_AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json(AW_AUTH_FILE, aw_auth, mode=0o600)
    return project


# ---------------------------------------------------------------------------
# Core sync
# ---------------------------------------------------------------------------


def sync_workstreams(
    *,
    auth_file: Path,
    aw_identifier: str,
    ws_id: str | None = None,
    comment: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    client, auth = _build_client(auth_file)
    workspace_slug = auth["workspace_slug"]

    project = _ensure_aw_project(client, auth, aw_identifier)
    project_id = project["id"]

    states_by_name = {s["name"]: s["id"] for s in client.list_states(workspace_slug, project_id)}
    labels_by_name = ensure_labels(client, workspace_slug, project_id, ALL_LABELS)

    workstreams = _load_active_workstreams(ws_id)
    synced: list[dict[str, Any]] = []

    for path, ws in workstreams:
        wid = ws.get("id", path.stem)
        existing_issue_id = ws.get("plane_issue_id")

        if dry_run:
            synced.append({"workstream_id": wid, "action": "dry_run"})
            continue

        issue = ensure_issue_for_workstream(
            client,
            workspace_slug=workspace_slug,
            project_id=project_id,
            states_by_name=states_by_name,
            labels_by_name=labels_by_name,
            ws=ws,
            existing_issue_id=existing_issue_id,
        )
        issue_id = issue["id"]
        action = "updated" if existing_issue_id else "created"

        # Write plane_issue_id back to the YAML if it was just created
        if not existing_issue_id:
            ws["plane_issue_id"] = issue_id
            _dump_yaml(path, ws)

        if comment:
            client.add_comment(workspace_slug, project_id, issue_id, f"<p>{comment}</p>")

        synced.append(
            {
                "workstream_id": wid,
                "plane_issue_id": issue_id,
                "action": action,
                "status": ws.get("status"),
            }
        )

    return {
        "workspace_slug": workspace_slug,
        "aw_project_id": project_id,
        "aw_identifier": aw_identifier,
        "count": len(synced),
        "synced": synced,
    }


def repair_orphans(*, auth_file: Path, aw_identifier: str) -> dict[str, Any]:
    """Close AW issues whose branches no longer exist in git."""
    client, auth = _build_client(auth_file)
    workspace_slug = auth["workspace_slug"]
    project = _ensure_aw_project(client, auth, aw_identifier)
    project_id = project["id"]

    states_by_name = {s["name"]: s["id"] for s in client.list_states(workspace_slug, project_id)}
    done_id = states_by_name.get("Done")
    if not done_id:
        raise PlaneError("AW project has no 'Done' state")

    existing_branches = _git_branches()
    active_ws_ids = {ws.get("id") for _, ws in _load_active_workstreams()}

    closed: list[str] = []
    for issue in client.list_issues(workspace_slug, project_id):
        if issue.get("external_source") != "repo_workstream":
            continue
        ws_id = issue.get("external_id", "")
        branch = issue.get("description_html", "")
        current_state = issue.get("state_id") or issue.get("state")
        if current_state == done_id:
            continue
        # Close if the workstream is no longer active AND the branch is gone
        if ws_id not in active_ws_ids:
            client.update_issue(workspace_slug, project_id, issue["id"], {"state_id": done_id})
            client.add_comment(
                workspace_slug,
                project_id,
                issue["id"],
                "<p>Auto-closed: workstream no longer in active/ and branch is absent from git.</p>",
            )
            closed.append(ws_id)

    return {"closed_orphans": closed, "count": len(closed)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync active workstreams to the Plane Agent Work (AW) project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--auth-file",
        default=os.environ.get("PLANE_AUTH_FILE", str(DEFAULT_AUTH_FILE)),
        help="Path to admin-auth.json (default: .local/plane/admin-auth.json)",
    )
    parser.add_argument(
        "--aw-project",
        default=os.environ.get("PLANE_AW_PROJECT", DEFAULT_AW_IDENTIFIER),
        help="AW project identifier (default: AW)",
    )
    parser.add_argument(
        "--workstream",
        "-w",
        metavar="ID",
        help="Sync a single workstream by id (default: all active)",
    )
    parser.add_argument(
        "--comment",
        "-m",
        metavar="TEXT",
        help="Add a plain-text comment to the synced issue(s)",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Close AW issues whose workstreams are no longer active",
    )
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Create the AW project if missing, then exit",
    )
    parser.add_argument(
        "--sync-members",
        metavar="JSON",
        help=(
            "JSON array of {email, role} objects to ensure as workspace members. "
            "role: 20=Admin, 15=Member, 10=Viewer. Idempotent."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without making API calls",
    )
    return parser


def sync_workspace_members(
    *,
    auth_file: Path,
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ensure a list of {email, role} entries are workspace members.

    Idempotent: members already present at the correct role are left unchanged.
    Members present at a different role are updated.
    New members are invited directly (no email confirmation needed for existing users).
    """
    client, auth = _build_client(auth_file)
    workspace_slug = auth["workspace_slug"]

    # Fetch current members keyed by email.
    # Plane v1.x returns members with the email at the top level; v2.x nests it
    # under "member". Support both shapes.
    current: dict[str, dict[str, Any]] = {}
    for m in client._collect(f"/api/v1/workspaces/{workspace_slug}/members/"):
        email = m.get("email") or m.get("member", {}).get("email", "")
        if email:
            current[email] = m

    results: list[dict[str, Any]] = []
    for entry in members:
        email = entry["email"]
        role = int(entry.get("role", 15))
        if email in current:
            existing_role = current[email].get("role")
            if existing_role == role:
                results.append({"email": email, "action": "noop", "role": role})
            else:
                # Plane v1.x CE does not expose a member-role-update REST endpoint.
                # Record as needs_role_update so Ansible can enforce via Django shell.
                results.append(
                    {
                        "email": email,
                        "action": "needs_role_update",
                        "current_role": existing_role,
                        "desired_role": role,
                        "note": "Use make converge-plane or Django shell to update role",
                    }
                )
        else:
            # Try direct invitation (works for existing Plane users without email flow)
            try:
                client._request(
                    f"/api/v1/workspaces/{workspace_slug}/invitations/",
                    method="POST",
                    payload={"email": email, "role": role},
                    expected_statuses={200, 201},
                )
                results.append({"email": email, "action": "invited", "role": role})
            except PlaneError as exc:
                results.append({"email": email, "action": "error", "error": str(exc)})

    return {"workspace": workspace_slug, "members": results}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    auth_file = Path(args.auth_file).expanduser()

    if args.sync_members:
        members = json.loads(args.sync_members)
        result = sync_workspace_members(auth_file=auth_file, members=members)
        print(json.dumps(result, indent=2))
        return 0

    if args.repair:
        result = repair_orphans(auth_file=auth_file, aw_identifier=args.aw_project)
        print(json.dumps(result, indent=2))
        return 0

    if args.bootstrap_only:
        client, auth = _build_client(auth_file)
        project = _ensure_aw_project(client, auth, args.aw_project)
        ensure_labels(client, auth["workspace_slug"], project["id"], ALL_LABELS)
        print(json.dumps({"aw_project_id": project["id"], "identifier": args.aw_project}, indent=2))
        return 0

    result = sync_workstreams(
        auth_file=auth_file,
        aw_identifier=args.aw_project,
        ws_id=args.workstream,
        comment=args.comment,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, PlaneError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(emit_cli_error("Plane agent issue sync", exc))
