#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.runtime_assurance import (
    ServiceAttestationNotFoundError,
    collect_declared_live_attestations,
    collect_declared_live_service_attestation,
)


def render_table(payload: dict[str, object]) -> str:
    services = payload.get("services", [])
    if not isinstance(services, list):
        return ""
    rows = [("service", "status", "host", "endpoint", "route", "receipt")]
    for item in services:
        if not isinstance(item, dict):
            continue
        rows.append(
            (
                str(item.get("service_id", "")),
                str(item.get("status", "")),
                str(item.get("host_witness", {}).get("status", "")),
                str(item.get("endpoint_proof", {}).get("status", "")),
                str(item.get("route_proof", {}).get("status", "")),
                str(item.get("receipt_witness", {}).get("status", "")),
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    rendered = []
    for index, row in enumerate(rows):
        rendered.append("  ".join(value.ljust(widths[column]) for column, value in enumerate(row)))
        if index == 0:
            rendered.append("  ".join("-" * widths[column] for column in range(len(widths))))
    return "\n".join(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect declared-to-live service attestation for the active service catalog."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--service")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--world-state-dsn")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--format", choices=("json", "table"), default="table")
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--max-workers", type=int, default=16)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.service:
            payload = collect_declared_live_service_attestation(
                args.service,
                repo_root=args.repo_root,
                environment=args.environment,
                world_state_dsn=args.world_state_dsn,
                timeout_seconds=args.timeout_seconds,
            )
            wrapper = {
                "schema_version": "1.0.0",
                "environment": args.environment,
                "services": [payload],
                "summary": {
                    "total": 1,
                    "attested": 1 if payload["status"] == "attested" else 0,
                    "missing": 0 if payload["status"] == "attested" else 1,
                },
            }
        else:
            wrapper = collect_declared_live_attestations(
                repo_root=args.repo_root,
                environment=args.environment,
                world_state_dsn=args.world_state_dsn,
                timeout_seconds=args.timeout_seconds,
                max_workers=args.max_workers,
            )
    except ServiceAttestationNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    output = json.dumps(wrapper, indent=2, sort_keys=True) if args.format == "json" else render_table(wrapper)
    if args.output_file:
        args.output_file.parent.mkdir(parents=True, exist_ok=True)
        args.output_file.write_text(output + "\n", encoding="utf-8")
    print(output)
    summary = wrapper.get("summary", {})
    if isinstance(summary, dict) and int(summary.get("missing", 0)) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
