#!/usr/bin/env python3
"""Run the repository validation gate defined in config/validation-gate.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import parallel_check
from scripts.session_workspace import resolve_session_workspace


DEFAULT_MANIFEST = Path("config/validation-gate.json")
DEFAULT_STATUS_FILE = Path(".local/validation-gate/last-run.json")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the repository validation gate from config/validation-gate.json."
    )
    parser.add_argument(
        "checks",
        nargs="*",
        help="Specific gate checks to run. Defaults to every configured check.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to the validation gate manifest.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace to mount into the check runner containers.",
    )
    parser.add_argument(
        "--docker-binary",
        default=os.environ.get("DOCKER_BIN", "docker"),
        help="Docker-compatible binary to use for execution.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="Maximum parallel checks. Defaults to the number of requested checks.",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_STATUS_FILE,
        help="Write the last-run status payload to this file.",
    )
    parser.add_argument(
        "--source",
        default="manual",
        help="Execution source label recorded in the status payload.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Emit the final status payload as JSON after the human-readable summary.",
    )
    return parser.parse_args(argv)


def load_gate_manifest(manifest_path: Path) -> tuple[dict[str, Any], dict[str, parallel_check.CheckDefinition]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"validation gate manifest {manifest_path} must contain a JSON object")
    return payload, parallel_check.load_manifest(manifest_path)


def resolve_requested_checks(
    manifest: dict[str, parallel_check.CheckDefinition],
    requested_labels: list[str],
) -> list[parallel_check.CheckDefinition]:
    if not requested_labels:
        return [manifest[label] for label in sorted(manifest)]
    return parallel_check.resolve_checks(manifest, requested_labels, run_all=False)


def build_status_payload(
    *,
    source: str,
    workspace: Path,
    manifest_path: Path,
    selected_checks: list[parallel_check.CheckDefinition],
    manifest_metadata: dict[str, Any],
    results: list[parallel_check.CheckResult],
) -> dict[str, Any]:
    passed = all(result.status == "passed" for result in results)
    session_workspace = resolve_session_workspace(repo_root=workspace)
    return {
        "status": "passed" if passed else "failed",
        "source": source,
        "workspace": str(workspace.resolve()),
        "session_workspace": {
            "session_id": session_workspace.session_id,
            "session_slug": session_workspace.session_slug,
            "local_state_root": session_workspace.local_state_root,
            "nats_prefix": session_workspace.nats_prefix,
            "state_namespace": session_workspace.state_namespace,
        },
        "manifest": str(manifest_path.resolve()),
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "checks": [
            {
                "id": result.label,
                "severity": manifest_metadata[result.label].get("severity", "error"),
                "description": manifest_metadata[result.label].get("description", ""),
                "status": result.status,
                "returncode": result.returncode,
                "duration_seconds": round(result.duration_seconds, 2),
                "docker_command": result.docker_command,
            }
            for result in results
        ],
        "requested_checks": [check.label for check in selected_checks],
    }


def write_status(status_file: Path, payload: dict[str, Any]) -> None:
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    manifest_metadata, manifest = load_gate_manifest(args.manifest)
    checks = resolve_requested_checks(manifest, args.checks)
    results = parallel_check.run_checks(
        checks,
        args.workspace.resolve(),
        args.docker_binary,
        args.jobs,
    )
    parallel_check.print_summary(results)

    payload = build_status_payload(
        source=args.source,
        workspace=args.workspace,
        manifest_path=args.manifest,
        selected_checks=checks,
        manifest_metadata=manifest_metadata,
        results=results,
    )
    write_status(args.status_file, payload)

    if args.print_json:
        print(json.dumps(payload, indent=2))

    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
