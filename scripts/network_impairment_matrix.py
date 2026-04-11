#!/usr/bin/env python3
"""Render and validate the ADR 0189 network impairment matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.faults import (
    build_network_impairment_report,
    load_network_impairment_matrix,
    render_network_impairment_report,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(
    *,
    repo_path: str,
    target_class: str = "",
    service: str = "",
    output_format: str = "json",
    report_file: str | None = None,
) -> dict:
    repo_root = Path(repo_path)
    matrix_path = repo_root / "config" / "network-impairment-matrix.yaml"
    catalog = load_network_impairment_matrix(matrix_path)
    report = build_network_impairment_report(
        catalog=catalog,
        target_class=target_class.strip() or None,
        service=service.strip() or None,
    )
    report["matrix_path"] = str(matrix_path)
    report_path = (
        Path(report_file) if report_file else repo_root / ".local" / "network-impairment-matrix" / "latest.json"
    )
    report["report_file"] = str(report_path)
    _write_json(report_path, report)
    report["rendered_output"] = render_network_impairment_report(report, output_format=output_format)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the ADR 0189 network impairment matrix.")
    parser.add_argument("--repo-path", default=str(REPO_ROOT))
    parser.add_argument("--target-class", default="")
    parser.add_argument("--service", default="")
    parser.add_argument("--format", choices=("json", "text", "markdown"), default="json")
    parser.add_argument("--report-file", help="Optional JSON report destination.")
    parser.add_argument("--validate", action="store_true", help="Validate the matrix and exit.")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    payload = main(
        repo_path=args.repo_path,
        target_class=args.target_class,
        service=args.service,
        output_format=args.format,
        report_file=args.report_file,
    )
    if args.validate:
        print("Network impairment matrix OK")
    elif args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["rendered_output"])
