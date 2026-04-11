#!/usr/bin/env python3
"""Run the repository validation gate defined in config/validation-gate.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import parallel_check
from scripts.session_workspace import resolve_session_workspace

try:
    from scripts import validation_lanes
except ModuleNotFoundError as exc:
    if exc.name != "yaml" or os.environ.get("LV3_RUN_GATE_PYYAML_BOOTSTRAPPED") == "1":
        raise
    helper_path = Path(__file__).resolve().with_name("run_python_with_packages.sh")
    if not helper_path.is_file():
        raise
    os.environ["LV3_RUN_GATE_PYYAML_BOOTSTRAPPED"] = "1"
    entrypoint = Path(sys.argv[0])
    if not entrypoint.is_absolute():
        entrypoint = (Path.cwd() / entrypoint).resolve()
    if not entrypoint.is_file():
        entrypoint = Path(__file__).resolve()
    os.execv(
        str(helper_path),
        [str(helper_path), "pyyaml", "--", str(entrypoint), *sys.argv[1:]],
    )
from scripts.validation_runner_contracts import (
    CONTRACT_CATALOG_PATH,
    build_runner_context,
    load_contract_catalog,
)


DEFAULT_MANIFEST = Path("config/validation-gate.json")
DEFAULT_STATUS_FILE = Path(".local/validation-gate/last-run.json")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the repository validation gate from config/validation-gate.json.")
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
        "--lane-catalog",
        type=Path,
        help="Optional validation-lane catalog. Defaults to <workspace>/config/validation-lanes.yaml.",
    )
    parser.add_argument(
        "--lane",
        action="append",
        help="Explicit validation lane to run. May be specified multiple times.",
    )
    parser.add_argument(
        "--all-lanes",
        action="store_true",
        help="Run every lane regardless of changed surfaces.",
    )
    parser.add_argument(
        "--base-ref",
        help="Explicit git base ref to diff against when auto-selecting lanes.",
    )
    parser.add_argument(
        "--source",
        default="manual",
        help="Execution source label recorded in the status payload.",
    )
    parser.add_argument(
        "--runner-id",
        default=os.environ.get("LV3_VALIDATION_RUNNER_ID", "controller-local-validation"),
        help="Validation runner contract id to attest and evaluate for this gate run.",
    )
    parser.add_argument(
        "--runner-contracts",
        type=Path,
        default=CONTRACT_CATALOG_PATH,
        help="Path to the validation runner contract catalog.",
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


def resolve_lane_catalog_path(args: argparse.Namespace) -> Path:
    if args.lane_catalog is not None:
        return args.lane_catalog
    return args.workspace.resolve() / "config" / "validation-lanes.yaml"


def _unique_in_order(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def resolve_changed_files_override() -> tuple[str, ...] | None:
    raw_payload = os.environ.get("LV3_VALIDATION_CHANGED_FILES_JSON", "").strip()
    if not raw_payload:
        return None
    payload = json.loads(raw_payload)
    if not isinstance(payload, list):
        raise ValueError("LV3_VALIDATION_CHANGED_FILES_JSON must be a JSON array")
    changed_files: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"LV3_VALIDATION_CHANGED_FILES_JSON[{index}] must be a non-empty string")
        changed_files.append(item.strip())
    return tuple(changed_files)


def resolve_gate_selection(
    *,
    args: argparse.Namespace,
    manifest: dict[str, parallel_check.CheckDefinition],
) -> tuple[
    list[parallel_check.CheckDefinition],
    validation_lanes.ValidationLaneCatalog | None,
    validation_lanes.ValidationLaneSelection | None,
]:
    lane_catalog_path = resolve_lane_catalog_path(args)
    requested_lanes = list(args.lane or ())
    if requested_lanes and args.checks:
        raise ValueError("choose explicit checks or explicit lanes, not both")

    if not lane_catalog_path.exists():
        return resolve_requested_checks(manifest, args.checks), None, None

    catalog = validation_lanes.load_catalog(
        catalog_path=lane_catalog_path,
        manifest_checks=set(manifest),
    )
    changed_files_override = resolve_changed_files_override()
    if changed_files_override is not None and not args.checks and not requested_lanes and not args.all_lanes:
        selection = validation_lanes.resolve_selection_from_changed_files(
            catalog,
            set(manifest),
            changed_files=changed_files_override,
            branch=validation_lanes.detect_current_branch(args.workspace.resolve()),
            base_ref=args.base_ref or os.environ.get("LV3_VALIDATION_BASE_REF"),
        )
    else:
        selection = validation_lanes.resolve_selection_for_repo(
            catalog,
            set(manifest),
            repo_root=args.workspace.resolve(),
            base_ref=args.base_ref,
            explicit_checks=tuple(args.checks),
            explicit_lanes=tuple(requested_lanes),
            force_all_lanes=args.all_lanes,
        )
    checks = [manifest[label] for label in selection.blocking_checks]
    return checks, catalog, selection


def _lane_status(check_statuses: list[str]) -> str:
    if not check_statuses:
        return "not_selected"
    if any(status == "timed_out" for status in check_statuses):
        return "timed_out"
    if any(status != "passed" for status in check_statuses):
        return "failed"
    return "passed"


def build_lane_results(
    *,
    catalog: validation_lanes.ValidationLaneCatalog | None,
    selection: validation_lanes.ValidationLaneSelection | None,
    results: list[parallel_check.CheckResult],
) -> list[dict[str, Any]]:
    if catalog is None or selection is None:
        return []

    result_by_label = {result.label: result for result in results}
    lane_results: list[dict[str, Any]] = []
    for lane_id, lane in catalog.lanes.items():
        selected = lane_id in selection.selected_lanes
        matched_surfaces = [surface for surface in selection.matched_surfaces if lane_id in surface.required_lanes]
        matched_files = _unique_in_order(
            [file_path for surface in matched_surfaces for file_path in surface.matched_files]
        )
        selected_checks = [check_id for check_id in lane.checks if check_id in selection.blocking_checks]
        statuses = [result_by_label[check_id].status for check_id in selected_checks if check_id in result_by_label]
        status = _lane_status(statuses) if selected else "not_selected"
        green_path_summary: str | None = None
        if selected and status == "passed":
            if matched_files:
                green_path_summary = (
                    f"{lane.title} passed for {len(matched_files)} changed file(s) via {', '.join(selected_checks)}."
                )
            else:
                green_path_summary = f"{lane.title} passed on the full-lane replay via {', '.join(selected_checks)}."
        lane_results.append(
            {
                "lane_id": lane_id,
                "title": lane.title,
                "description": lane.description,
                "status": status,
                "selected": selected,
                "selected_checks": selected_checks,
                "matched_files": list(matched_files),
                "matched_surfaces": [surface.as_dict() for surface in matched_surfaces],
                "green_path_summary": green_path_summary,
            }
        )
    return lane_results


def build_fast_global_results(
    *,
    selection: validation_lanes.ValidationLaneSelection | None,
    results: list[parallel_check.CheckResult],
    manifest_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    if selection is None:
        return []
    result_by_label = {result.label: result for result in results}
    payload: list[dict[str, Any]] = []
    for check_id in selection.fast_global_checks:
        result = result_by_label.get(check_id)
        if result is None:
            continue
        metadata = manifest_metadata.get(check_id, {})
        payload.append(
            {
                "id": check_id,
                "description": metadata.get("description", ""),
                "severity": metadata.get("severity", "error"),
                "status": result.status,
                "returncode": result.returncode,
            }
        )
    return payload


def build_status_payload(
    *,
    source: str,
    workspace: Path,
    manifest_path: Path,
    selected_checks: list[parallel_check.CheckDefinition],
    manifest_metadata: dict[str, Any],
    results: list[parallel_check.CheckResult],
    runner_context: dict[str, Any],
    selection: validation_lanes.ValidationLaneSelection | None = None,
    lane_results: list[dict[str, Any]] | None = None,
    lane_catalog_path: Path | None = None,
) -> dict[str, Any]:
    passed = all(result.status == "passed" for result in results)
    session_workspace = resolve_session_workspace(repo_root=workspace)
    payload: dict[str, Any] = {
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
        "executed_at": datetime.now(UTC).isoformat(),
        "runner": runner_context,
        "checks": [
            {
                "id": result.label,
                "severity": manifest_metadata[result.label].get("severity", "error"),
                "description": manifest_metadata[result.label].get("description", ""),
                "status": result.status,
                "returncode": result.returncode,
                "duration_seconds": round(result.duration_seconds, 2),
                "docker_command": result.docker_command,
                "runner_unavailable_reason": result.stderr if result.status == "runner_unavailable" else None,
            }
            for result in results
        ],
        "requested_checks": [check.label for check in selected_checks],
    }
    if selection is not None:
        payload["lane_catalog"] = str(lane_catalog_path.resolve()) if lane_catalog_path is not None else None
        payload["lane_selection"] = selection.as_dict()
        payload["lane_results"] = lane_results or []
        payload["fast_global_results"] = build_fast_global_results(
            selection=selection,
            results=results,
            manifest_metadata=manifest_metadata,
        )
    return payload


def write_status(status_file: Path, payload: dict[str, Any]) -> None:
    status_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f"{status_file.stem}-",
        suffix=status_file.suffix or ".json",
        dir=status_file.parent,
        delete=False,
        mode="w",
        encoding="utf-8",
    ) as temp_file:
        temp_file.write(json.dumps(payload, indent=2) + "\n")
        temp_path = Path(temp_file.name)
    temp_path.replace(status_file)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    manifest_metadata, manifest = load_gate_manifest(args.manifest)
    workspace = args.workspace.resolve()
    os.environ["LV3_VALIDATION_SOURCE"] = args.source
    checks, catalog, selection = resolve_gate_selection(args=args, manifest=manifest)
    if selection is not None:
        print(validation_lanes.render_selection_summary(selection))
    runner_catalog = load_contract_catalog(args.runner_contracts)
    runner_context = build_runner_context(
        runner_catalog,
        runner_id=args.runner_id,
        workspace=workspace,
        lanes=[check.label for check in checks],
        container_runtime_binary=args.docker_binary,
    )
    runner_unavailable_results = {
        check.label: parallel_check.CheckResult(
            label=check.label,
            status="runner_unavailable",
            returncode=69,
            duration_seconds=0.0,
            stdout="",
            stderr="; ".join(runner_context["lane_evaluations"].get(check.label, {}).get("reasons", [])),
            docker_command=[],
        )
        for check in checks
        if not runner_context["lane_evaluations"].get(check.label, {}).get("eligible", True)
    }
    runnable_checks = [check for check in checks if check.label not in runner_unavailable_results]
    executed_results = (
        parallel_check.run_checks(
            runnable_checks,
            workspace,
            args.docker_binary,
            args.jobs,
        )
        if runnable_checks
        else []
    )
    executed_by_label = {result.label: result for result in executed_results}
    results = [
        runner_unavailable_results[check.label]
        if check.label in runner_unavailable_results
        else executed_by_label[check.label]
        for check in checks
    ]
    parallel_check.print_summary(results)

    payload = build_status_payload(
        source=args.source,
        workspace=workspace,
        manifest_path=args.manifest,
        selected_checks=checks,
        manifest_metadata=manifest_metadata,
        results=results,
        runner_context=runner_context,
        selection=selection,
        lane_results=build_lane_results(catalog=catalog, selection=selection, results=results),
        lane_catalog_path=resolve_lane_catalog_path(args) if catalog is not None else None,
    )
    write_status(args.status_file, payload)

    if args.print_json:
        print(json.dumps(payload, indent=2))

    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
