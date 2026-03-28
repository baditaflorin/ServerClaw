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

from controller_automation_toolkit import emit_cli_error, load_json, write_json
from platform.ansible.plane import PlaneClient, PlaneError, ensure_issue_for_adr, parse_adr


def sync_adrs(
    *,
    auth_file: str,
    adr_dir: str,
    adr_ids: list[str] | None = None,
    summary_output: str | None = None,
) -> dict[str, Any]:
    auth = load_json(Path(auth_file).expanduser())
    client = PlaneClient(
        auth["base_url"],
        auth["api_token"],
        verify_ssl=bool(auth.get("verify_ssl", True)),
        timeout=120,
        max_rate_limit_retries=8,
    )
    if not client.verify_api_key():
        raise PlaneError(f"Plane API token in {auth_file} is not valid")
    workspace_slug = auth["workspace_slug"]
    project_id = auth["project_id"]
    states_by_name = {state.get("name"): state.get("id") for state in client.list_states(workspace_slug, project_id)}
    existing_issues = {
        issue.get("external_id"): issue
        for issue in client.list_issues(workspace_slug, project_id)
        if issue.get("external_source") == "repo_adr" and issue.get("external_id")
    }

    adr_root = Path(adr_dir).expanduser()
    adr_paths = sorted(adr_root.glob("[0-9][0-9][0-9][0-9]-*.md"))
    if adr_ids:
        wanted = {item.zfill(4) for item in adr_ids}
        adr_paths = [path for path in adr_paths if path.name[:4] in wanted]

    synced: list[dict[str, Any]] = []
    for path in adr_paths:
        record = parse_adr(path)
        issue = ensure_issue_for_adr(
            client,
            workspace_slug=workspace_slug,
            project_id=project_id,
            states_by_name=states_by_name,
            record=record,
            existing_issue=existing_issues.get(record.external_id),
        )
        existing_issues[record.external_id] = issue
        synced.append(
            {
                "adr_id": record.adr_id,
                "issue_id": issue.get("id"),
                "issue_name": issue.get("name"),
                "state_id": issue.get("state_id") or issue.get("state"),
            }
        )

    summary = {
        "workspace_slug": workspace_slug,
        "project_id": project_id,
        "count": len(synced),
        "synced": synced,
    }
    if summary_output:
        write_json(Path(summary_output).expanduser(), summary, mode=0o600)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize repo ADR markdown into Plane issues.")
    parser.add_argument("--auth-file", default=str(REPO_ROOT / ".local" / "plane" / "admin-auth.json"))
    parser.add_argument("--adr-dir", default=str(REPO_ROOT / "docs" / "adr"))
    parser.add_argument("--adr", action="append", help="Optional ADR id to sync. Repeat for multiple ids.")
    parser.add_argument("--summary-output", help="Optional JSON output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = sync_adrs(
        auth_file=args.auth_file,
        adr_dir=args.adr_dir,
        adr_ids=args.adr,
        summary_output=args.summary_output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, PlaneError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(emit_cli_error("Plane ADR sync", exc))
