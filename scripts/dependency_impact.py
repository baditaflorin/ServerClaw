#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys

from dependency_graph import (
    EDGE_TYPE_LABELS,
    compute_impact,
    dependency_summary,
    load_dependency_graph,
)
from controller_automation_toolkit import emit_cli_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect the LV3 service dependency graph.")
    parser.add_argument("--service", required=True, help="Service id to inspect.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser


def render_text(service_id: str) -> str:
    graph = load_dependency_graph(validate_schema=False)
    summary = dependency_summary(service_id, graph)
    impact = compute_impact(service_id, graph)
    lines = [
        f"Dependency summary for {service_id}:",
        f"  Recovery tier: {summary['tier']}",
        "  Depends on:",
    ]
    for edge_type in ("hard", "soft", "startup_only", "reads_from"):
        services = summary["depends_on"][edge_type]
        if services:
            lines.append(f"    - {EDGE_TYPE_LABELS[edge_type]}: {', '.join(services)}")
    if all(not summary["depends_on"][edge_type] for edge_type in summary["depends_on"]):
        lines.append("    - none")

    lines.extend(
        [
            f"Impact of {service_id} failure:",
            "  Direct hard failures:",
            "    - " + ", ".join(impact.direct_hard) if impact.direct_hard else "    - none",
            "  Transitive hard failures:",
            "    - " + ", ".join(impact.transitive_hard) if impact.transitive_hard else "    - none",
            "  Direct soft degradations:",
            "    - " + ", ".join(impact.direct_soft) if impact.direct_soft else "    - none",
            "  Startup-only risk:",
            "    - " + ", ".join(impact.direct_startup_only) if impact.direct_startup_only else "    - none",
            "  Read-path degradation:",
            "    - " + ", ".join(impact.direct_reads_from) if impact.direct_reads_from else "    - none",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        graph = load_dependency_graph(validate_schema=False)
        if args.json:
            print(json.dumps(dependency_summary(args.service, graph), indent=2))
            return 0
        print(render_text(args.service))
        return 0
    except Exception as exc:
        return emit_cli_error("dependency impact", exc)


if __name__ == "__main__":
    sys.exit(main())
