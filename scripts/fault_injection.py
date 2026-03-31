#!/usr/bin/env python3
"""Run the ADR 0171 controlled fault-injection suite."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import resolve_repo_local_path, write_json
from glitchtip_event import emit_glitchtip_event
from platform.faults import DockerSocketClient, FaultInjector, is_first_sunday_utc, load_scenario_catalog
from platform.ledger import LedgerWriter


DEFAULT_LEDGER_FILE = ".local/state/ledger/fault-injection.events.jsonl"


def maybe_read_secret_path(repo_root: Path, secret_id: str) -> str | None:
    manifest_path = repo_root / "config" / "controller-local-secrets.json"
    if not manifest_path.exists():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    secret = payload.get("secrets", {}).get(secret_id)
    if secret is None or secret.get("kind") != "file":
        return None
    secret_path = resolve_repo_local_path(secret["path"], repo_root=repo_root)
    if not secret_path.exists():
        return None
    return secret_path.read_text(encoding="utf-8").strip()


def post_json_webhook(url: str, payload: dict[str, Any]) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 300:
            raise RuntimeError(f"webhook POST failed with HTTP {response.status}")


def parse_scenario_names(values: list[str] | None, csv_names: str) -> list[str]:
    names: list[str] = []
    for value in values or []:
        candidate = value.strip()
        if candidate:
            names.append(candidate)
    for value in csv_names.split(","):
        candidate = value.strip()
        if candidate:
            names.append(candidate)
    return list(dict.fromkeys(names))


def build_summary(report: dict[str, Any]) -> str:
    if report["status"] == "skipped":
        return f"ADR 0171 fault injection skipped: {report['reason']}"
    lines = [
        f"ADR 0171 fault injection [{report['status']}]: "
        f"{report['passed']}/{report['scenario_count']} scenarios passed in "
        f"{report['duration_seconds']:.1f}s"
    ]
    for scenario in report.get("results", []):
        lines.append(
            f"- {scenario['name']}: {scenario['status']} "
            f"({scenario['duration_seconds']:.1f}s)"
        )
    return "\n".join(lines)


def publish_notifications(repo_root: Path, report: dict[str, Any]) -> None:
    mattermost_url = (
        os.environ.get("LV3_MATTERMOST_WEBHOOK_URL", "").strip()
        or maybe_read_secret_path(repo_root, "mattermost_platform_findings_webhook_url")
    )
    if mattermost_url:
        post_json_webhook(mattermost_url, {"text": build_summary(report)})

    if report["status"] in {"passed", "skipped"}:
        return

    glitchtip_url = (
        os.environ.get("LV3_GLITCHTIP_EVENT_URL", "").strip()
        or maybe_read_secret_path(repo_root, "glitchtip_platform_findings_event_url")
    )
    if glitchtip_url:
        emit_glitchtip_event(
            glitchtip_url,
            {
                "message": "ADR 0171 fault injection detected a regression",
                "level": "error",
                "tags": {
                    "workflow": "fault-injection",
                    "scenario_count": report["scenario_count"],
                },
                "extra": {
                    "report_file": report.get("report_file"),
                    "failed_scenarios": [
                        scenario["name"]
                        for scenario in report.get("results", [])
                        if scenario.get("status") != "passed"
                    ],
                },
            },
        )


def main(
    *,
    repo_path: str,
    scenario_names: list[str] | None = None,
    schedule_guard: str = "",
    dry_run: bool = False,
    publish_notifications_enabled: bool = False,
    report_file: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    docker_socket = Path("/var/run/docker.sock")
    if not docker_socket.exists():
        return {
            "status": "blocked",
            "reason": "docker socket is not mounted on the worker",
            "expected_socket_path": str(docker_socket),
        }

    if schedule_guard and schedule_guard == "first_sunday" and not is_first_sunday_utc():
        return {
            "status": "skipped",
            "reason": "scheduled run deferred because today is not the first Sunday in UTC",
            "schedule_guard": schedule_guard,
        }

    catalog = load_scenario_catalog(repo_root / "config" / "fault-scenarios.yaml")
    selected_names = scenario_names or list(catalog.scheduled_scenario_names or catalog.scenarios)
    missing = [name for name in selected_names if name not in catalog.scenarios]
    if missing:
        return {
            "status": "blocked",
            "reason": "unknown fault scenario requested",
            "missing_scenarios": missing,
        }

    if dry_run:
        return {
            "status": "planned",
            "scenario_count": len(selected_names),
            "selected_scenarios": selected_names,
            "schedule_guard": schedule_guard or None,
        }

    scenarios = [catalog.scenarios[name] for name in selected_names]
    report_path = Path(report_file) if report_file else catalog.report_dir / "latest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    ledger_path = repo_root / DEFAULT_LEDGER_FILE
    injector = FaultInjector(
        docker_client=DockerSocketClient(),
        ledger_writer=LedgerWriter(file_path=ledger_path, nats_publisher=None),
    )
    suite = injector.run_suite(scenarios).as_dict()
    suite["report_file"] = str(report_path)
    write_json(report_path, suite, indent=2)

    if publish_notifications_enabled:
        publish_notifications(repo_root, suite)
    return suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0171 controlled fault-injection suite.")
    parser.add_argument("--repo-path", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--scenario", action="append", dest="scenarios", help="Scenario name to execute.")
    parser.add_argument("--scenario-names", default="", help="Comma-separated scenario names.")
    parser.add_argument("--schedule-guard", choices=("first_sunday",), default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish-notifications", action="store_true")
    parser.add_argument("--report-file", help="Optional JSON report destination.")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    payload = main(
        repo_path=args.repo_path,
        scenario_names=parse_scenario_names(args.scenarios, args.scenario_names),
        schedule_guard=args.schedule_guard,
        dry_run=args.dry_run,
        publish_notifications_enabled=args.publish_notifications,
        report_file=args.report_file,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
