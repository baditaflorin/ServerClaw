#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import emit_cli_error, write_json
from platform.ansible.plane import bootstrap_plane


def load_text(path: str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return None
    return resolved.read_text(encoding="utf-8").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap Plane admin, workspace, project, and API auth.")
    parser.add_argument("--base-url", required=True, help="Controller-facing Plane base URL.")
    parser.add_argument("--admin-email", required=True, help="Bootstrap admin email address.")
    parser.add_argument("--password-file", required=True, help="Path to the bootstrap admin password file.")
    parser.add_argument("--spec-file", required=True, help="Path to the JSON bootstrap specification.")
    parser.add_argument("--verify-ssl", action="store_true", help="Verify TLS certificates.")
    parser.add_argument("--existing-token-file", help="Optional existing API token file to reuse when valid.")
    parser.add_argument("--auth-json-output", required=True, help="Path to the persisted auth JSON file.")
    parser.add_argument("--api-token-output", required=True, help="Path to the persisted API token file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = load_text(args.password_file)
    if not password:
        raise ValueError(f"Missing Plane password in {args.password_file}")
    spec = json.loads(Path(args.spec_file).expanduser().read_text(encoding="utf-8"))
    existing_token = load_text(args.existing_token_file)

    summary = bootstrap_plane(
        base_url=args.base_url,
        admin_email=args.admin_email,
        admin_password=password,
        spec=spec,
        verify_ssl=args.verify_ssl,
        existing_api_token=existing_token,
    )

    auth_payload = {
        "base_url": args.base_url.rstrip("/"),
        "email": args.admin_email,
        "password": password,
        "api_token": summary["api_token"],
        "verify_ssl": args.verify_ssl,
        "workspace_id": summary["workspace"]["id"],
        "workspace_name": summary["workspace"]["name"],
        "workspace_slug": summary["workspace"]["slug"],
        "project_id": summary["project"]["id"],
        "project_name": summary["project"]["name"],
        "project_identifier": summary["project"]["identifier"],
    }
    write_json(Path(args.auth_json_output).expanduser(), auth_payload, mode=0o600)
    token_path = Path(args.api_token_output).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(summary["api_token"] + "\n", encoding="utf-8")
    token_path.chmod(0o600)
    print(json.dumps(auth_payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise SystemExit(emit_cli_error("Plane bootstrap", exc))
