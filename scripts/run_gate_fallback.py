#!/usr/bin/env python3
"""Reuse synced remote gate status and rerun only unresolved checks locally."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RUN_GATE_PATH = SCRIPT_DIR / "run_gate.py"
DEFAULT_MANIFEST = Path("config/validation-gate.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rerun only unresolved gate checks after a remote gate fallback."
    )
    parser.add_argument(
        "checks",
        nargs="*",
        help="Explicit checks to run when no synced remote gate payload is available.",
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
        help="Workspace to validate.",
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
        help="Maximum parallel checks. Defaults to the run_gate.py default.",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        required=True,
        help="Write the final merged gate status payload to this file.",
    )
    parser.add_argument(
        "--lane-catalog",
        type=Path,
        help="Optional validation lane catalog path.",
    )
    parser.add_argument(
        "--base-ref",
        help="Explicit git base ref to diff against when auto-selecting lanes.",
    )
    parser.add_argument(
        "--source",
        default="local-fallback",
        help="Execution source label recorded in the final status payload.",
    )
    parser.add_argument(
        "--all-lanes",
        action="store_true",
        help="Run every lane regardless of changed surfaces when no remote payload is present.",
    )
    return parser.parse_args(argv)


def resolve_status_file(path: Path, workspace: Path) -> Path:
    if path.is_absolute():
        return path
    return workspace / path


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    raw_payload = path.read_text(encoding="utf-8")
    if not raw_payload.strip():
        return None
    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        print(
            f"run_gate_fallback: ignoring unreadable JSON status payload at {path}: {exc}",
            file=sys.stderr,
        )
        return None


def is_remote_gate_payload(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    source = str(payload.get("source", ""))
    checks = payload.get("checks")
    return source.startswith("build-server") and isinstance(checks, list)


def unresolved_checks(payload: dict[str, Any]) -> list[str]:
    checks = payload.get("checks", [])
    return [
        str(check["id"])
        for check in checks
        if isinstance(check, dict) and str(check.get("status", "")) != "passed"
    ]


def build_run_gate_command(
    *,
    python_binary: str,
    workspace: Path,
    manifest: Path,
    docker_binary: str,
    jobs: int,
    status_file: Path,
    lane_catalog: Path | None,
    base_ref: str | None,
    source: str,
    all_lanes: bool,
    checks: list[str],
) -> list[str]:
    command = [
        python_binary,
        str(RUN_GATE_PATH),
        "--workspace",
        str(workspace),
        "--manifest",
        str(manifest),
        "--docker-binary",
        docker_binary,
        "--status-file",
        str(status_file),
        "--source",
        source,
    ]
    if jobs:
        command.extend(["--jobs", str(jobs)])
    if lane_catalog is not None:
        command.extend(["--lane-catalog", str(lane_catalog)])
    if base_ref:
        command.extend(["--base-ref", base_ref])
    if all_lanes:
        command.append("--all-lanes")
    command.extend(checks)
    return command


def lane_status(check_statuses: list[str]) -> str:
    if not check_statuses:
        return "not_selected"
    if any(status == "timed_out" for status in check_statuses):
        return "timed_out"
    if any(status != "passed" for status in check_statuses):
        return "failed"
    return "passed"


def merge_lane_results(
    *,
    remote_lane_results: Any,
    local_lane_results: Any,
    merged_statuses: dict[str, str],
) -> Any:
    if not isinstance(remote_lane_results, list):
        return local_lane_results

    merged_results: list[dict[str, Any]] = []
    for lane in remote_lane_results:
        if not isinstance(lane, dict):
            continue
        updated_lane = dict(lane)
        if not updated_lane.get("selected", False):
            updated_lane["status"] = "not_selected"
            updated_lane["green_path_summary"] = None
            merged_results.append(updated_lane)
            continue

        selected_checks = [str(item) for item in updated_lane.get("selected_checks", [])]
        statuses = [
            merged_statuses[check_id]
            for check_id in selected_checks
            if check_id in merged_statuses
        ]
        status = lane_status(statuses)
        updated_lane["status"] = status
        if status == "passed":
            matched_files = updated_lane.get("matched_files") or []
            title = str(updated_lane.get("title", "Validation lane"))
            if matched_files:
                updated_lane["green_path_summary"] = (
                    f"{title} passed for {len(matched_files)} changed file(s) via "
                    f"{', '.join(selected_checks)}."
                )
            else:
                updated_lane["green_path_summary"] = (
                    f"{title} passed on the full-lane replay via {', '.join(selected_checks)}."
                )
        else:
            updated_lane["green_path_summary"] = None
        merged_results.append(updated_lane)
    return merged_results


def merge_fast_global_results(
    *,
    remote_fast_global_results: Any,
    local_fast_global_results: Any,
    merged_statuses: dict[str, str],
    merged_returncodes: dict[str, int],
) -> Any:
    if not isinstance(remote_fast_global_results, list):
        return local_fast_global_results

    merged_results: list[dict[str, Any]] = []
    for item in remote_fast_global_results:
        if not isinstance(item, dict):
            continue
        check_id = str(item.get("id", ""))
        updated_item = dict(item)
        if check_id in merged_statuses:
            updated_item["status"] = merged_statuses[check_id]
        if check_id in merged_returncodes:
            updated_item["returncode"] = merged_returncodes[check_id]
        merged_results.append(updated_item)
    return merged_results


def merge_status_payloads(
    *,
    remote_payload: dict[str, Any],
    local_payload: dict[str, Any],
) -> dict[str, Any]:
    remote_checks = [
        check for check in remote_payload.get("checks", []) if isinstance(check, dict)
    ]
    local_checks = [
        check for check in local_payload.get("checks", []) if isinstance(check, dict)
    ]
    local_by_id = {str(check["id"]): check for check in local_checks if "id" in check}
    remote_ids = [str(check["id"]) for check in remote_checks if "id" in check]

    merged_checks = [
        local_by_id.get(str(check["id"]), check)
        for check in remote_checks
        if "id" in check
    ]
    merged_checks.extend(
        check for check_id, check in local_by_id.items() if check_id not in remote_ids
    )

    merged_statuses = {
        str(check["id"]): str(check.get("status", "failed"))
        for check in merged_checks
        if "id" in check
    }
    merged_returncodes = {
        str(check["id"]): int(check.get("returncode", 1))
        for check in merged_checks
        if "id" in check
    }

    merged_payload = dict(remote_payload)
    merged_payload.update(
        {
            "status": (
                "passed"
                if merged_checks and all(
                    str(check.get("status", "")) == "passed" for check in merged_checks
                )
                else "failed"
            ),
            "source": local_payload.get("source", remote_payload.get("source", "local-fallback")),
            "workspace": local_payload.get("workspace", remote_payload.get("workspace")),
            "session_workspace": local_payload.get(
                "session_workspace", remote_payload.get("session_workspace")
            ),
            "manifest": local_payload.get("manifest", remote_payload.get("manifest")),
            "executed_at": local_payload.get("executed_at", remote_payload.get("executed_at")),
            "runner": local_payload.get("runner", remote_payload.get("runner")),
            "checks": merged_checks,
            "requested_checks": remote_payload.get(
                "requested_checks",
                local_payload.get("requested_checks", [check["id"] for check in merged_checks]),
            ),
            "lane_catalog": remote_payload.get(
                "lane_catalog", local_payload.get("lane_catalog")
            ),
            "lane_selection": remote_payload.get(
                "lane_selection", local_payload.get("lane_selection")
            ),
            "lane_results": merge_lane_results(
                remote_lane_results=remote_payload.get("lane_results"),
                local_lane_results=local_payload.get("lane_results"),
                merged_statuses=merged_statuses,
            ),
            "fast_global_results": merge_fast_global_results(
                remote_fast_global_results=remote_payload.get("fast_global_results"),
                local_fast_global_results=local_payload.get("fast_global_results"),
                merged_statuses=merged_statuses,
                merged_returncodes=merged_returncodes,
            ),
        }
    )
    return merged_payload


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f"{path.stem}-",
        suffix=path.suffix or ".json",
        dir=path.parent,
        delete=False,
        mode="w",
        encoding="utf-8",
    ) as temp_file:
        temp_file.write(json.dumps(payload, indent=2) + "\n")
        temp_path = Path(temp_file.name)
    temp_path.replace(path)


def run_fallback_gate(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace = args.workspace.resolve()
    status_file = resolve_status_file(args.status_file, workspace)
    manifest = args.manifest if args.manifest.is_absolute() else workspace / args.manifest
    lane_catalog = (
        args.lane_catalog
        if args.lane_catalog is None or args.lane_catalog.is_absolute()
        else workspace / args.lane_catalog
    )

    prior_payload = load_optional_json(status_file)
    use_remote_payload = is_remote_gate_payload(prior_payload)
    rerun_checks = unresolved_checks(prior_payload) if use_remote_payload else []

    if rerun_checks:
        print(
            "run_gate_fallback: rerunning unresolved remote checks locally: "
            + ", ".join(rerun_checks)
        )
    elif prior_payload is not None and not use_remote_payload:
        print(
            "run_gate_fallback: ignoring stale non-remote gate status and running the "
            "requested local checks."
        )

    python_binary = (
        os.environ.get("LV3_VALIDATE_PYTHON_BIN")
        or sys.executable
        or shutil.which("python3")
        or "python3"
    )
    checks_to_run = rerun_checks or list(args.checks)

    with tempfile.NamedTemporaryFile(
        prefix="run-gate-fallback-",
        suffix=".json",
        dir=status_file.parent,
        delete=False,
    ) as temp_file:
        temp_status_path = Path(temp_file.name)

    command = build_run_gate_command(
        python_binary=python_binary,
        workspace=workspace,
        manifest=manifest,
        docker_binary=args.docker_binary,
        jobs=args.jobs,
        status_file=temp_status_path,
        lane_catalog=lane_catalog,
        base_ref=args.base_ref,
        source=args.source,
        all_lanes=args.all_lanes,
        checks=checks_to_run,
    )
    completed = subprocess.run(
        command,
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)

    local_payload = load_optional_json(temp_status_path)
    if local_payload is None:
        temp_status_path.unlink(missing_ok=True)
        return completed.returncode

    final_payload = (
        merge_status_payloads(remote_payload=prior_payload, local_payload=local_payload)
        if use_remote_payload and rerun_checks
        else local_payload
    )
    write_status(status_file, final_payload)
    temp_status_path.unlink(missing_ok=True)

    if use_remote_payload and rerun_checks:
        print(
            "run_gate_fallback: merged local rerun with synced remote gate status at "
            f"{status_file}"
        )

    return 0 if final_payload.get("status") == "passed" else (completed.returncode or 1)


def main(argv: list[str] | None = None) -> int:
    return run_fallback_gate(argv)


if __name__ == "__main__":
    raise SystemExit(main())
