#!/usr/bin/env python3
"""Generate Prometheus HTTPS/TLS assurance targets and alert rules with block markers.

Generates:
  - config/prometheus/file_sd/https_tls_targets.yml
  - config/prometheus/rules/https_tls_alerts.yml

Each service block is wrapped in:
  # BEGIN SERVICE: <service_id>
  # END SERVICE: <service_id>
markers so that decommission_service.py can surgically remove them without
corrupting the surrounding YAML (Amendment 5 — ADR 0396).

Usage:
    python3 scripts/generate_https_tls_assurance.py --write
    python3 scripts/generate_https_tls_assurance.py --check    # exits 1 if files would change
    python3 scripts/generate_https_tls_assurance.py --dry-run  # print diff without writing
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from controller_automation_toolkit import emit_cli_error
from https_tls_assurance_targets import (
    DEFAULT_ENVIRONMENT,
    PROMETHEUS_ALERTS_PATH,
    PROMETHEUS_TARGETS_PATH,
    build_prometheus_alert_rules,
    build_prometheus_targets,
    discover_https_tls_targets,
)


GENERATED_HEADER = (
    "# AUTO-GENERATED from config/certificate-catalog.json — do not edit manually\n"
    "# Run: python3 scripts/generate_https_tls_assurance.py --write\n"
)


def _group_targets_by_service(targets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in targets:
        by_service[t["service_id"]].append(t)
    return by_service


def build_targets_text_with_markers(targets: list[dict[str, Any]]) -> str:
    """Generate https_tls_targets.yml as text with # BEGIN/END SERVICE markers."""
    import yaml  # PyYAML is available in the platform scripts venv

    by_service = _group_targets_by_service(targets)

    parts = [GENERATED_HEADER]
    for service_id in sorted(by_service):
        rows = build_prometheus_targets(by_service[service_id])
        block = yaml.dump(rows, default_flow_style=False, allow_unicode=True)
        parts.append(f"# BEGIN SERVICE: {service_id}\n")
        parts.append(block)
        parts.append(f"# END SERVICE: {service_id}\n")

    return "".join(parts)


def build_alerts_text_with_markers(targets: list[dict[str, Any]]) -> str:
    """Generate https_tls_alerts.yml as text with # BEGIN/END SERVICE markers.

    The alert rules list is indented at 6 spaces inside the
    ``groups[0].rules`` array, matching the YAML structure.
    """
    import yaml

    by_service = _group_targets_by_service(targets)

    parts = [
        GENERATED_HEADER,
        "groups:\n",
        "  - name: https_tls_assurance\n",
        "    interval: 1m\n",
        "    rules:\n\n",
    ]

    for service_id in sorted(by_service):
        service_targets = by_service[service_id]
        alert_payload = build_prometheus_alert_rules(service_targets)
        rules = alert_payload["groups"][0]["rules"]
        rules_yaml = yaml.dump(rules, default_flow_style=False, allow_unicode=True)
        # Indent each rule line at 6 spaces (inside groups[0].rules)
        indented_lines = []
        for line in rules_yaml.rstrip("\n").split("\n"):
            indented_lines.append(("      " + line) if line.strip() else "")
        indented = "\n".join(indented_lines)

        parts.append(f"# BEGIN SERVICE: {service_id}\n")
        parts.append(indented + "\n")
        parts.append(f"# END SERVICE: {service_id}\n")

    return "".join(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the committed Prometheus HTTPS/TLS assurance targets and alert rules."
    )
    parser.add_argument("--env", default=DEFAULT_ENVIRONMENT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="Write generated files to disk.")
    group.add_argument("--check", action="store_true", help="Exit non-zero if files would change (CI mode).")
    group.add_argument("--dry-run", action="store_true", help="Print what would be written without writing.")
    parser.add_argument("--print-targets-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    targets = discover_https_tls_targets(environment=args.env)

    targets_text = build_targets_text_with_markers(targets)
    alerts_text = build_alerts_text_with_markers(targets)

    outputs = {
        PROMETHEUS_TARGETS_PATH: targets_text,
        PROMETHEUS_ALERTS_PATH: alerts_text,
    }

    repo_root = Path(__file__).resolve().parents[1]

    def _read_existing(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    changed = [p for p, content in outputs.items() if _read_existing(p) != content]

    if args.write:
        for path, content in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    if args.check:
        if changed:
            for p in changed:
                rel = str(p.relative_to(repo_root))
                print(f"OUT OF DATE: {rel}; run generate_https_tls_assurance.py --write", file=sys.stderr)
            return 1

    if args.dry_run:
        for path, content in outputs.items():
            rel = str(path.relative_to(repo_root))
            status = "CHANGED" if path in changed else "unchanged"
            print(f"--- {rel}  [{status}] ---")
            print(content[:800])
            if len(content) > 800:
                print(f"  ... ({len(content)} bytes total)")
            print()

    if args.print_targets_json:
        print(json.dumps(targets, indent=2))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(emit_cli_error("generate https tls assurance", exc))
