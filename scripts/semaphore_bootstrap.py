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
from platform.ansible.semaphore import SemaphoreClient, apply_bootstrap_spec


def load_text(path: str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return None
    return resolved.read_text(encoding="utf-8").strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap Semaphore project, inventory, templates, and API auth.")
    parser.add_argument("--base-url", required=True, help="Controller-facing Semaphore base URL.")
    parser.add_argument("--username", required=True, help="Bootstrap admin username.")
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
        raise ValueError(f"Missing Semaphore password in {args.password_file}")
    spec = json.loads(Path(args.spec_file).expanduser().read_text(encoding="utf-8"))
    existing_token = load_text(args.existing_token_file)

    client = SemaphoreClient(args.base_url, verify_ssl=args.verify_ssl)
    summary = apply_bootstrap_spec(
        client,
        spec,
        username=args.username,
        password=password,
        verify_ssl=args.verify_ssl,
        existing_api_token=existing_token,
    )

    auth_payload = {
        "base_url": args.base_url.rstrip("/"),
        "username": args.username,
        "password": password,
        "api_token": summary.api_token,
        "verify_ssl": args.verify_ssl,
        "project_id": int(summary.project["id"]),
        "project_name": summary.project["name"],
        "inventory_id": int(summary.inventory["id"]),
        "inventory_name": summary.inventory["name"],
        "repository_id": int(summary.repository["id"]),
        "repository_name": summary.repository["name"],
        "templates": {
            template["name"]: {
                "id": int(template["id"]),
                "playbook": template["playbook"],
            }
            for template in summary.templates
        },
    }
    write_json(Path(args.auth_json_output).expanduser(), auth_payload, mode=0o600)
    Path(args.api_token_output).expanduser().parent.mkdir(parents=True, exist_ok=True)
    Path(args.api_token_output).expanduser().write_text(summary.api_token + "\n", encoding="utf-8")
    Path(args.api_token_output).expanduser().chmod(0o600)
    print(json.dumps(auth_payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise SystemExit(emit_cli_error("Semaphore bootstrap", exc))
