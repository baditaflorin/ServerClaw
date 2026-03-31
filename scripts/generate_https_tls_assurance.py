#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from controller_automation_toolkit import emit_cli_error
from https_tls_assurance_targets import (
    DEFAULT_ENVIRONMENT,
    PROMETHEUS_ALERTS_PATH,
    PROMETHEUS_TARGETS_PATH,
    build_prometheus_alert_rules,
    build_prometheus_targets,
    discover_https_tls_targets,
)
from slo_tracking import write_yaml


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the committed Prometheus HTTPS/TLS assurance targets and alert rules."
    )
    parser.add_argument("--env", default=DEFAULT_ENVIRONMENT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--print-targets-json", action="store_true")
    return parser


def serialized_yaml(path: Path, payload: object) -> str:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir) / path.name
        write_yaml(temp_path, payload)
        return temp_path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.write and args.check:
        raise ValueError("choose either --write or --check")

    targets = discover_https_tls_targets(environment=args.env)
    target_payload = build_prometheus_targets(targets)
    alert_payload = build_prometheus_alert_rules(targets)

    if args.write:
        write_yaml(PROMETHEUS_TARGETS_PATH, target_payload)
        write_yaml(PROMETHEUS_ALERTS_PATH, alert_payload)

    if args.check:
        expected_targets = serialized_yaml(PROMETHEUS_TARGETS_PATH, target_payload)
        expected_alerts = serialized_yaml(PROMETHEUS_ALERTS_PATH, alert_payload)
        if PROMETHEUS_TARGETS_PATH.read_text(encoding="utf-8") != expected_targets:
            raise ValueError(f"{PROMETHEUS_TARGETS_PATH} is out of date; run generate_https_tls_assurance.py --write")
        if PROMETHEUS_ALERTS_PATH.read_text(encoding="utf-8") != expected_alerts:
            raise ValueError(f"{PROMETHEUS_ALERTS_PATH} is out of date; run generate_https_tls_assurance.py --write")

    if args.print_targets_json:
        print(json.dumps(targets, indent=2))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(emit_cli_error("generate https tls assurance", exc))
