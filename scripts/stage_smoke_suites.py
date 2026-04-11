#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_bool, require_list, require_mapping, require_str

from controller_automation_toolkit import emit_cli_error, load_json
from environment_catalog import environment_choices, primary_environment

import integration_suite


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "config" / "stage-smoke-suites.json"
SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "stage-smoke-suites.schema.json"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
DEFAULT_REPORT_DIR = ".local/stage-smoke-suites"
ALLOWED_RUNNERS = {"integration_suite"}


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    normalized: list[str] = []
    for index, item in enumerate(items):
        normalized.append(require_str(item, f"{path}[{index}]"))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{path} must not contain duplicates")
    return normalized


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def load_stage_smoke_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    return load_json(path)


def load_service_catalog(path: Path = SERVICE_CATALOG_PATH) -> dict[str, Any]:
    return load_json(path)


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.chmod(temp_path, 0o666)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def maybe_relative_to_repo(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def build_service_index(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    services = require_list(catalog.get("services"), "service-capability-catalog.services")
    index: dict[str, dict[str, Any]] = {}
    for service_index, service in enumerate(services):
        service = require_mapping(service, f"service-capability-catalog.services[{service_index}]")
        service_id = require_str(service.get("id"), f"service-capability-catalog.services[{service_index}].id")
        index[service_id] = service
    return index


def environment_binding(service: dict[str, Any], environment: str) -> dict[str, Any] | None:
    environments = service.get("environments")
    if not isinstance(environments, dict):
        return None
    binding = environments.get(environment)
    if not isinstance(binding, dict):
        return None
    return binding


def validate_stage_smoke_catalog(
    catalog: dict[str, Any] | None = None,
    service_catalog: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    catalog = catalog or load_stage_smoke_catalog()
    service_catalog = service_catalog or load_service_catalog()

    if catalog.get("$schema") != "docs/schema/stage-smoke-suites.schema.json":
        raise ValueError(
            "config/stage-smoke-suites.json.$schema must reference docs/schema/stage-smoke-suites.schema.json"
        )

    try:
        import jsonschema
    except ModuleNotFoundError:  # pragma: no cover - optional runtime helper
        jsonschema = None

    if jsonschema is not None:
        jsonschema.validate(instance=catalog, schema=load_json(SCHEMA_PATH))

    suites = require_list(catalog.get("suites"), "stage-smoke-suites.suites")
    if not suites:
        raise ValueError("stage-smoke-suites.suites must not be empty")

    service_index = build_service_index(service_catalog)
    suite_index: dict[str, dict[str, Any]] = {}

    for suite_offset, suite in enumerate(suites):
        suite = require_mapping(suite, f"stage-smoke-suites.suites[{suite_offset}]")
        suite_id = require_str(suite.get("id"), f"stage-smoke-suites.suites[{suite_offset}].id")
        if suite_id in suite_index:
            raise ValueError(f"stage-smoke-suites.suites must not declare duplicate suite '{suite_id}'")

        service_id = require_str(
            suite.get("service_id"),
            f"stage-smoke-suites.suites[{suite_offset}].service_id",
        )
        if service_id not in service_index:
            raise ValueError(f"stage-smoke-suites.suites[{suite_offset}] references unknown service '{service_id}'")

        environment = require_str(
            suite.get("environment"),
            f"stage-smoke-suites.suites[{suite_offset}].environment",
        )
        service = service_index[service_id]
        binding = environment_binding(service, environment)
        if binding is None:
            raise ValueError(
                f"stage-smoke-suites.suites[{suite_offset}] references missing environment '{environment}' on service '{service_id}'"
            )

        runner = require_str(suite.get("runner"), f"stage-smoke-suites.suites[{suite_offset}].runner")
        if runner not in ALLOWED_RUNNERS:
            raise ValueError(
                f"stage-smoke-suites.suites[{suite_offset}].runner must be one of {sorted(ALLOWED_RUNNERS)}"
            )
        mode = require_str(suite.get("mode"), f"stage-smoke-suites.suites[{suite_offset}].mode")
        if mode not in integration_suite.MODE_MARKERS:
            raise ValueError(
                f"stage-smoke-suites.suites[{suite_offset}].mode must be one of {sorted(integration_suite.MODE_MARKERS)}"
            )
        require_str(suite.get("description"), f"stage-smoke-suites.suites[{suite_offset}].description")
        targets = require_string_list(
            suite.get("targets"),
            f"stage-smoke-suites.suites[{suite_offset}].targets",
        )
        required_service_ids = []
        if "required_service_ids" in suite:
            required_service_ids = require_string_list(
                suite.get("required_service_ids"),
                f"stage-smoke-suites.suites[{suite_offset}].required_service_ids",
            )
            unknown_service_ids = sorted(set(required_service_ids) - set(service_index))
            if unknown_service_ids:
                raise ValueError(
                    f"stage-smoke-suites.suites[{suite_offset}].required_service_ids references unknown services: "
                    + ", ".join(unknown_service_ids)
                )

        normalized = {
            "id": suite_id,
            "service_id": service_id,
            "environment": environment,
            "description": suite["description"],
            "runner": runner,
            "mode": mode,
            "targets": targets,
        }
        if required_service_ids:
            normalized["required_service_ids"] = required_service_ids
        if "notes" in suite:
            normalized["notes"] = require_str(suite.get("notes"), f"stage-smoke-suites.suites[{suite_offset}].notes")
        suite_index[suite_id] = normalized

    for service_id, service in service_index.items():
        environments = service.get("environments")
        if not isinstance(environments, dict):
            continue
        for environment, binding in environments.items():
            if not isinstance(binding, dict):
                continue
            smoke_suite_ids = binding.get("smoke_suite_ids", [])
            if smoke_suite_ids:
                smoke_suite_ids = require_string_list(
                    smoke_suite_ids,
                    f"service-capability-catalog.services.{service_id}.environments.{environment}.smoke_suite_ids",
                )
            stage_ready = bool(binding.get("stage_ready", False))
            if "stage_ready" in binding:
                require_bool(
                    binding.get("stage_ready"),
                    f"service-capability-catalog.services.{service_id}.environments.{environment}.stage_ready",
                )
            if stage_ready and not smoke_suite_ids:
                raise ValueError(
                    f"service '{service_id}' environment '{environment}' is stage_ready but has no smoke_suite_ids"
                )
            for suite_id in smoke_suite_ids:
                suite = suite_index.get(suite_id)
                if suite is None:
                    raise ValueError(
                        f"service '{service_id}' environment '{environment}' references unknown smoke suite '{suite_id}'"
                    )
                if suite["service_id"] != service_id:
                    raise ValueError(
                        f"service '{service_id}' environment '{environment}' references smoke suite '{suite_id}' "
                        f"owned by service '{suite['service_id']}'"
                    )
                if suite["environment"] != environment:
                    raise ValueError(
                        f"service '{service_id}' environment '{environment}' references smoke suite '{suite_id}' "
                        f"for environment '{suite['environment']}'"
                    )

    return suite_index


def resolve_declared_suite_ids(
    service_catalog: dict[str, Any],
    service_id: str,
    environment: str,
) -> list[str]:
    service_index = build_service_index(service_catalog)
    if service_id not in service_index:
        raise ValueError(f"unknown service '{service_id}'")
    binding = environment_binding(service_index[service_id], environment)
    if binding is None:
        raise ValueError(f"service '{service_id}' does not declare environment '{environment}'")
    smoke_suite_ids = binding.get("smoke_suite_ids", [])
    if not smoke_suite_ids:
        raise ValueError(f"service '{service_id}' environment '{environment}' does not declare smoke_suite_ids")
    return require_string_list(
        smoke_suite_ids,
        f"service-capability-catalog.services.{service_id}.environments.{environment}.smoke_suite_ids",
    )


def default_report_path(repo_root: Path, service_id: str, environment: str) -> Path:
    return repo_root / DEFAULT_REPORT_DIR / f"{environment}-{service_id}.json"


def suite_report_path(aggregate_path: Path, suite_id: str) -> Path:
    return aggregate_path.parent / f"{aggregate_path.stem}-{suite_id}.json"


def build_summary_text(summary: dict[str, Any]) -> str:
    return f"{summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed, {summary.get('skipped', 0)} skipped"


def build_receipt_smoke_suite_entry(result: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    return {
        "suite_id": result["suite_id"],
        "service_id": result["service_id"],
        "environment": result["environment"],
        "status": result["status"],
        "executed_at": result["executed_at"],
        "summary": result["summary_text"],
        "report_ref": maybe_relative_to_repo(Path(result["report_file"]), repo_root),
    }


def execute_integration_suite(
    *,
    repo_root: Path,
    suite: dict[str, Any],
    environment: str,
    report_file: Path,
    service_id: str,
) -> tuple[int, dict[str, Any]]:
    try:
        return integration_suite.run_suite(
            repo_root=repo_root,
            mode=suite["mode"],
            environment=environment,
            report_file=report_file,
            fail_on_missing_targets=True,
            selection=suite["targets"],
            required_service_ids=list(suite.get("required_service_ids", [service_id])),
        )
    except ModuleNotFoundError as exc:
        if exc.name != "pytest":
            raise

    command = [
        "uv",
        "run",
        "--with-requirements",
        str(repo_root / "requirements" / "integration-tests.txt"),
        "python",
        str(repo_root / "scripts" / "integration_suite.py"),
        "--mode",
        suite["mode"],
        "--environment",
        environment,
        "--report-file",
        str(report_file),
    ]
    for target in suite["targets"]:
        command.extend(["--target", target])
    for required_service_id in list(suite.get("required_service_ids", [service_id])):
        command.extend(["--required-service-id", required_service_id])

    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=dict(os.environ),
    )
    if report_file.exists():
        payload = json.loads(report_file.read_text(encoding="utf-8"))
        return (0 if payload["status"] == "passed" else 1), payload
    raise RuntimeError(
        completed.stderr.strip() or completed.stdout.strip() or "stage smoke suite integration execution failed"
    )


def run_stage_smoke_suites(
    *,
    repo_root: Path,
    suite_ids: list[str],
    service_id: str,
    environment: str,
    report_file: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    catalog = load_stage_smoke_catalog(repo_root / "config" / "stage-smoke-suites.json")
    service_catalog = load_service_catalog(repo_root / "config" / "service-capability-catalog.json")
    suite_index = validate_stage_smoke_catalog(catalog, service_catalog)

    requested_suite_ids = list(dict.fromkeys(suite_ids))
    if not requested_suite_ids:
        raise ValueError("at least one suite id is required")

    aggregate_path = report_file or default_report_path(repo_root, service_id, environment)
    results: list[dict[str, Any]] = []
    summary = {"passed": 0, "failed": 0, "skipped": 0, "total": 0}

    for suite_id in requested_suite_ids:
        suite = suite_index.get(suite_id)
        if suite is None:
            raise ValueError(f"unknown smoke suite '{suite_id}'")
        if suite["service_id"] != service_id:
            raise ValueError(f"suite '{suite_id}' belongs to service '{suite['service_id']}', not '{service_id}'")
        if suite["environment"] != environment:
            raise ValueError(f"suite '{suite_id}' belongs to environment '{suite['environment']}', not '{environment}'")

        integration_report = suite_report_path(aggregate_path, suite_id)
        _exit_code, payload = execute_integration_suite(
            repo_root=repo_root,
            suite=suite,
            environment=environment,
            report_file=integration_report,
            service_id=service_id,
        )
        result = {
            "suite_id": suite_id,
            "service_id": service_id,
            "environment": environment,
            "status": payload["status"],
            "executed_at": payload["executed_at"],
            "description": suite["description"],
            "runner": suite["runner"],
            "mode": suite["mode"],
            "targets": suite["targets"],
            "required_service_ids": list(suite.get("required_service_ids", [service_id])),
            "report_file": str(integration_report.resolve()),
            "summary": payload["summary"],
            "summary_text": build_summary_text(payload["summary"]),
            "integration_suite": payload,
        }
        results.append(result)
        if result["status"] == "passed":
            summary["passed"] += 1
        elif result["status"] == "skipped":
            summary["skipped"] += 1
        else:
            summary["failed"] += 1
        summary["total"] += 1

    aggregate_status = "passed" if summary["failed"] == 0 and summary["skipped"] == 0 else "failed"
    aggregate_payload = {
        "status": aggregate_status,
        "service": service_id,
        "environment": environment,
        "executed_at": iso_now(),
        "repo_root": str(repo_root.resolve()),
        "suite_ids": requested_suite_ids,
        "summary": summary,
        "suites": results,
        "receipt_smoke_suites": [build_receipt_smoke_suite_entry(result, repo_root) for result in results],
    }
    write_report(aggregate_path, aggregate_payload)
    return (0 if aggregate_status == "passed" else 1), aggregate_payload


def list_suites(catalog: dict[str, Any] | None = None) -> int:
    suite_index = validate_stage_smoke_catalog(catalog or load_stage_smoke_catalog(), load_service_catalog())
    for suite_id in sorted(suite_index):
        suite = suite_index[suite_id]
        print(f"{suite_id}: {suite['service_id']} [{suite['environment']}] {suite['runner']} / {suite['mode']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and run repo-managed stage smoke suites.")
    parser.add_argument(
        "--validate", action="store_true", help="Validate the smoke suite catalog and service bindings."
    )
    parser.add_argument("--list", action="store_true", help="List declared smoke suites.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root that contains config/stage-smoke-suites.json.",
    )
    parser.add_argument("--service", help="Service id whose declared smoke suites should run.")
    parser.add_argument(
        "--environment",
        choices=environment_choices(),
        default=primary_environment(),
        help="Environment binding to resolve for --service.",
    )
    parser.add_argument(
        "--suite-id",
        action="append",
        default=[],
        help="Explicit suite id to run. Repeat as needed.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=None,
        help="Write the aggregate report to this path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()

    try:
        if args.validate:
            validate_stage_smoke_catalog(
                load_stage_smoke_catalog(repo_root / "config" / "stage-smoke-suites.json"),
                load_service_catalog(repo_root / "config" / "service-capability-catalog.json"),
            )
            print("Stage smoke suites OK")
            return 0

        if args.list:
            catalog = load_stage_smoke_catalog(repo_root / "config" / "stage-smoke-suites.json")
            service_catalog = load_service_catalog(repo_root / "config" / "service-capability-catalog.json")
            validate_stage_smoke_catalog(catalog, service_catalog)
            for suite_id in sorted(item["id"] for item in catalog["suites"]):
                suite = next(entry for entry in catalog["suites"] if entry["id"] == suite_id)
                print(f"{suite_id}: {suite['service_id']} [{suite['environment']}] {suite['runner']} / {suite['mode']}")
            return 0

        explicit_suite_ids = list(args.suite_id)
        if args.service:
            service_catalog = load_service_catalog(repo_root / "config" / "service-capability-catalog.json")
            declared_suite_ids = resolve_declared_suite_ids(service_catalog, args.service, args.environment)
            suite_ids = explicit_suite_ids or declared_suite_ids
            exit_code, payload = run_stage_smoke_suites(
                repo_root=repo_root,
                suite_ids=suite_ids,
                service_id=args.service,
                environment=args.environment,
                report_file=args.report_file,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return exit_code

        if explicit_suite_ids:
            catalog = load_stage_smoke_catalog(repo_root / "config" / "stage-smoke-suites.json")
            service_catalog = load_service_catalog(repo_root / "config" / "service-capability-catalog.json")
            suite_index = validate_stage_smoke_catalog(catalog, service_catalog)
            first_suite = suite_index[explicit_suite_ids[0]]
            exit_code, payload = run_stage_smoke_suites(
                repo_root=repo_root,
                suite_ids=explicit_suite_ids,
                service_id=first_suite["service_id"],
                environment=first_suite["environment"],
                report_file=args.report_file,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return exit_code

        raise ValueError("choose --validate, --list, --service, or --suite-id")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Stage smoke suites", exc)


if __name__ == "__main__":
    raise SystemExit(main())
