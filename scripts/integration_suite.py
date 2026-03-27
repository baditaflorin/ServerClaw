#!/usr/bin/env python3
"""Run the ADR 0111 integration test suite with environment-aware skip logic."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from environment_catalog import environment_choices, primary_environment


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ".local/integration-tests"
SERVICE_IDS = (
    "keycloak",
    "grafana",
    "netbox",
    "openbao",
    "postgres",
    "windmill",
)
MODE_MARKERS = {
    "gate": "integration and not mutation and not destructive",
    "nightly": "integration and not destructive",
    "all": "integration",
    "destructive": "integration and destructive",
}
ENVIRONMENT_CHOICES = environment_choices()
DEFAULT_ENVIRONMENT = primary_environment()


@dataclass(frozen=True)
class SuiteTargets:
    gateway_url: str | None
    keycloak_url: str | None
    grafana_url: str | None
    netbox_url: str | None
    openbao_url: str | None
    postgres_dsn: str | None
    windmill_url: str | None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "gateway_url": self.gateway_url,
                "keycloak_url": self.keycloak_url,
                "grafana_url": self.grafana_url,
                "netbox_url": self.netbox_url,
                "openbao_url": self.openbao_url,
                "postgres_dsn": self.postgres_dsn,
                "windmill_url": self.windmill_url,
            }.items()
            if value
        }


class SuiteReporter:
    """Collect per-test outcomes without depending on extra pytest plugins."""

    def __init__(self) -> None:
        self.results: dict[str, dict[str, Any]] = {}

    def pytest_runtest_logreport(self, report) -> None:  # pragma: no cover - exercised via pytest
        if report.when not in {"setup", "call"}:
            return

        entry = self.results.setdefault(
            report.nodeid,
            {
                "nodeid": report.nodeid,
                "outcome": "skipped",
                "duration_seconds": 0.0,
                "longrepr": "",
            },
        )

        if report.when == "setup" and report.skipped:
            entry["outcome"] = "skipped"
            entry["duration_seconds"] = round(report.duration, 3)
            entry["longrepr"] = str(report.longrepr)
            return

        if report.when == "call":
            entry["outcome"] = report.outcome
            entry["duration_seconds"] = round(report.duration, 3)
            if report.failed:
                entry["longrepr"] = str(report.longrepr)

    def summary(self) -> dict[str, int]:
        totals = {"passed": 0, "failed": 0, "skipped": 0}
        for entry in self.results.values():
            outcome = entry["outcome"]
            if outcome == "failed":
                totals["failed"] += 1
            elif outcome == "passed":
                totals["passed"] += 1
            else:
                totals["skipped"] += 1
        totals["total"] = sum(totals.values())
        return totals


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ADR 0111 integration suite.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Repository root that contains tests/integration.",
    )
    parser.add_argument(
        "--mode",
        choices=sorted(MODE_MARKERS),
        default="all",
        help="Test selection mode.",
    )
    parser.add_argument(
        "--environment",
        choices=ENVIRONMENT_CHOICES,
        default=os.environ.get("LV3_INTEGRATION_ENVIRONMENT", DEFAULT_ENVIRONMENT),
        help="Environment whose URLs should be resolved from the service catalog.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=None,
        help="Write a JSON report to this path.",
    )
    parser.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="Extra argument passed through to pytest. Repeat as needed.",
    )
    parser.add_argument(
        "--fail-on-missing-targets",
        action="store_true",
        help="Treat an unavailable integration environment as a failure instead of a skip.",
    )
    return parser.parse_args(argv or sys.argv[1:])


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value.rstrip("/")


def env_override(name: str) -> str | None:
    return normalize_url(os.environ.get(name))


def load_service_catalog(repo_root: Path) -> dict[str, Any]:
    return load_json(repo_root / "config" / "service-capability-catalog.json")


def find_service(catalog: dict[str, Any], service_id: str) -> dict[str, Any] | None:
    for service in catalog.get("services", []):
        if service.get("id") == service_id:
            return service
    return None


def resolve_service_url(catalog: dict[str, Any], service_id: str, environment: str) -> str | None:
    service = find_service(catalog, service_id)
    if service is None:
        return None

    envs = service.get("environments", {})
    env_entry = envs.get(environment)
    if isinstance(env_entry, dict) and env_entry.get("status") == "active":
        return normalize_url(env_entry.get("url"))

    if environment == DEFAULT_ENVIRONMENT:
        return normalize_url(service.get("public_url") or service.get("internal_url"))
    return None


def resolve_targets(repo_root: Path, environment: str) -> SuiteTargets:
    catalog = load_service_catalog(repo_root)
    return SuiteTargets(
        gateway_url=env_override("LV3_INTEGRATION_GATEWAY_URL"),
        keycloak_url=env_override("LV3_INTEGRATION_KEYCLOAK_URL")
        or resolve_service_url(catalog, "keycloak", environment),
        grafana_url=env_override("LV3_INTEGRATION_GRAFANA_URL")
        or resolve_service_url(catalog, "grafana", environment),
        netbox_url=env_override("LV3_INTEGRATION_NETBOX_URL")
        or resolve_service_url(catalog, "netbox", environment),
        openbao_url=env_override("LV3_INTEGRATION_OPENBAO_URL")
        or resolve_service_url(catalog, "openbao", environment),
        postgres_dsn=os.environ.get("LV3_INTEGRATION_POSTGRES_DSN")
        or resolve_service_url(catalog, "postgres", environment),
        windmill_url=env_override("LV3_INTEGRATION_WINDMILL_URL")
        or resolve_service_url(catalog, "windmill", environment),
    )


def targets_available(targets: SuiteTargets) -> bool:
    return any(targets.as_dict().values())


def report_path(repo_root: Path, requested: Path | None, mode: str, environment: str) -> Path:
    if requested is not None:
        return requested
    return repo_root / DEFAULT_REPORT_DIR / f"{environment}-{mode}.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_skipped_payload(
    *,
    mode: str,
    environment: str,
    repo_root: Path,
    targets: SuiteTargets,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "skipped",
        "mode": mode,
        "environment": environment,
        "executed_at": iso_now(),
        "repo_root": str(repo_root.resolve()),
        "reason": reason,
        "targets": targets.as_dict(),
        "summary": {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
        },
        "tests": [],
    }


def prepare_environment(mode: str, environment: str, repo_root: Path, targets: SuiteTargets) -> None:
    os.environ.setdefault("LV3_INTEGRATION_ENVIRONMENT", environment)
    os.environ.setdefault("LV3_INTEGRATION_REPO_ROOT", str(repo_root.resolve()))
    os.environ.setdefault("LV3_INTEGRATION_ENABLE_NETWORK_TESTS", "1")
    if mode == "gate":
        os.environ.setdefault("LV3_RUN_SECRET_ROTATION_TEST", "0")
        os.environ.setdefault("LV3_ENABLE_FAILOVER_TEST", "0")
        os.environ.setdefault("LV3_ENABLE_BACKUP_RECOVERY_TEST", "0")
    elif mode == "nightly":
        os.environ.setdefault("LV3_RUN_SECRET_ROTATION_TEST", "1")
        os.environ.setdefault("LV3_ENABLE_FAILOVER_TEST", "0")
        os.environ.setdefault("LV3_ENABLE_BACKUP_RECOVERY_TEST", "0")
    elif mode == "destructive":
        os.environ.setdefault("LV3_RUN_SECRET_ROTATION_TEST", "1")
        os.environ.setdefault("LV3_ENABLE_FAILOVER_TEST", "1")
        os.environ.setdefault("LV3_ENABLE_BACKUP_RECOVERY_TEST", "1")

    if targets.gateway_url:
        os.environ.setdefault("LV3_INTEGRATION_GATEWAY_URL", targets.gateway_url)
    if targets.keycloak_url:
        os.environ.setdefault("LV3_INTEGRATION_KEYCLOAK_URL", targets.keycloak_url)
    if targets.grafana_url:
        os.environ.setdefault("LV3_INTEGRATION_GRAFANA_URL", targets.grafana_url)
    if targets.netbox_url:
        os.environ.setdefault("LV3_INTEGRATION_NETBOX_URL", targets.netbox_url)
    if targets.openbao_url:
        os.environ.setdefault("LV3_INTEGRATION_OPENBAO_URL", targets.openbao_url)
    if targets.postgres_dsn:
        os.environ.setdefault("LV3_INTEGRATION_POSTGRES_DSN", targets.postgres_dsn)
    if targets.windmill_url:
        os.environ.setdefault("LV3_INTEGRATION_WINDMILL_URL", targets.windmill_url)


def run_pytest(repo_root: Path, mode: str, extra_args: list[str]) -> tuple[int, SuiteReporter, float]:
    import pytest

    reporter = SuiteReporter()
    started = time.monotonic()
    pytest_args = [
        str(repo_root / "tests" / "integration"),
        "-rA",
        "-m",
        MODE_MARKERS[mode],
        *extra_args,
    ]
    exit_code = pytest.main(pytest_args, plugins=[reporter])
    return int(exit_code), reporter, time.monotonic() - started


def build_result_payload(
    *,
    repo_root: Path,
    mode: str,
    environment: str,
    exit_code: int,
    reporter: SuiteReporter,
    duration_seconds: float,
    targets: SuiteTargets,
) -> dict[str, Any]:
    summary = reporter.summary()
    status = "failed" if exit_code != 0 or summary["failed"] else "passed"
    return {
        "status": status,
        "mode": mode,
        "environment": environment,
        "executed_at": iso_now(),
        "repo_root": str(repo_root.resolve()),
        "marker_expression": MODE_MARKERS[mode],
        "duration_seconds": round(duration_seconds, 3),
        "targets": targets.as_dict(),
        "summary": summary,
        "tests": sorted(reporter.results.values(), key=lambda item: item["nodeid"]),
    }


def run_suite(
    *,
    repo_root: Path,
    mode: str,
    environment: str,
    extra_args: list[str] | None = None,
    fail_on_missing_targets: bool = False,
    report_file: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    targets = resolve_targets(repo_root, environment)
    if not targets_available(targets):
        payload = build_skipped_payload(
            mode=mode,
            environment=environment,
            repo_root=repo_root,
            targets=targets,
            reason=(
                f"no active {environment} integration endpoints found in config/service-capability-catalog.json "
                "and no LV3_INTEGRATION_* overrides were supplied"
            ),
        )
        write_report(report_path(repo_root, report_file, mode, environment), payload)
        return (1 if fail_on_missing_targets else 0), payload

    prepare_environment(mode, environment, repo_root, targets)
    exit_code, reporter, duration_seconds = run_pytest(repo_root, mode, list(extra_args or []))
    payload = build_result_payload(
        repo_root=repo_root,
        mode=mode,
        environment=environment,
        exit_code=exit_code,
        reporter=reporter,
        duration_seconds=duration_seconds,
        targets=targets,
    )
    write_report(report_path(repo_root, report_file, mode, environment), payload)
    return (0 if payload["status"] == "passed" else 1), payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    exit_code, payload = run_suite(
        repo_root=args.repo_root.resolve(),
        mode=args.mode,
        environment=args.environment,
        extra_args=args.pytest_arg,
        fail_on_missing_targets=args.fail_on_missing_targets,
        report_file=args.report_file,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
