#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, repo_path, write_json
from drift_lib import isoformat, utc_now
from https_tls_assurance_targets import DEFAULT_ENVIRONMENT, discover_https_tls_targets
from public_surface_scan import (
    SEVERITY_CODES,
    SEVERITY_ORDER,
    component_summary,
    run_testssl_scans,
    summarize_findings,
)


DEFAULT_RECEIPT_DIR = repo_path("receipts", "https-tls-assurance")
DEFAULT_ARTIFACTS_ROOT = repo_path(".local", "https-tls-assurance")
DEFAULT_TESTSSL_IMAGE = "ghcr.io/testssl/testssl.sh:latest"
DEFAULT_TIMEOUT_SECONDS = 60


def relative_repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(repo_path().resolve()))


def build_report(
    *,
    scan_id: str,
    environment: str,
    targets: list[dict[str, Any]],
    tls_results: dict[str, dict[str, Any]],
    findings: list[dict[str, Any]],
    started_at: float,
    artifacts_dir: Path,
) -> dict[str, Any]:
    counts = summarize_findings(findings)
    if counts["critical"]:
        status = "critical"
    elif counts["high"]:
        status = "high"
    elif counts["medium"] or counts["low"]:
        status = "warn"
    else:
        status = "clean"

    target_rows: list[dict[str, Any]] = []
    for target in targets:
        target_findings = [item for item in findings if item["target"] == target["id"]]
        target_rows.append(
            {
                "id": target["id"],
                "service_id": target["service_id"],
                "scope": target["scope"],
                "exposure": target["exposure"],
                "display_url": target["display_url"],
                "certificate_id": target["certificate_id"],
                "expected_issuer": target["expected_issuer"],
                "finding_counts": summarize_findings(target_findings),
            }
        )

    return {
        "schema_version": "1.0.0",
        "scan_id": scan_id,
        "generated_at": isoformat(utc_now()),
        "environment": environment,
        "artifacts_dir": relative_repo_path(artifacts_dir),
        "targets": target_rows,
        "tls_scans": tls_results,
        "findings": sorted(
            findings,
            key=lambda item: (
                SEVERITY_ORDER.index(item["severity"]),
                item["target"],
                item["finding_id"],
            ),
        ),
        "summary": {
            "target_count": len(targets),
            "duration_seconds": round(time.monotonic() - started_at, 2),
            "status": status,
            "status_code": SEVERITY_CODES[status],
            "finding_counts": counts,
            "components": {
                "tls": component_summary(findings, "tls"),
            },
        },
    }


def write_receipt(receipt_dir: Path, report: dict[str, Any]) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    path = receipt_dir / f"{report['scan_id']}.json"
    write_json(path, report, indent=2, sort_keys=True)
    return path


def run_scan(
    *,
    environment: str,
    receipt_dir: Path,
    artifacts_root: Path,
    testssl_image: str,
    pull_images: bool,
    skip_testssl: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    scan_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    started_at = time.monotonic()
    targets = discover_https_tls_targets(environment=environment)
    artifacts_dir = artifacts_root / scan_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    findings: list[dict[str, Any]] = []
    if skip_testssl:
        tls_results = {}
    else:
        public_surface_targets = [
            {
                "fqdn": target["id"],
                "finding_target": target["id"],
                "display_name": target["display_url"],
                "scan_slug": target["id"],
                "url": target["display_url"],
                "testssl_url": target["testssl_url"],
                "testssl_ip": target["testssl_ip"],
            }
            for target in targets
        ]
        tls_results, tls_findings = run_testssl_scans(
            scan_id=scan_id,
            targets=public_surface_targets,
            artifacts_dir=artifacts_dir,
            image=testssl_image,
            pull_images=pull_images,
            timeout_seconds=timeout_seconds,
        )
        findings.extend(
            [
                {
                    **finding,
                    "target": finding["target"],
                }
                for finding in tls_findings
            ]
        )

    report = build_report(
        scan_id=scan_id,
        environment=environment,
        targets=targets,
        tls_results=tls_results,
        findings=findings,
        started_at=started_at,
        artifacts_dir=artifacts_dir,
    )
    receipt_path = write_receipt(receipt_dir, report)
    report["receipt_path"] = relative_repo_path(receipt_path)
    return report


def build_parser() -> argparse.ArgumentParser:
    timeout_default = int(os.environ.get("HTTPS_TLS_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    parser = argparse.ArgumentParser(description="Run the ADR 0249 HTTPS/TLS assurance scan and write a receipt.")
    parser.add_argument("--env", default=DEFAULT_ENVIRONMENT)
    parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--artifacts-root", type=Path, default=DEFAULT_ARTIFACTS_ROOT)
    parser.add_argument("--testssl-image", default=os.environ.get("HTTPS_TLS_TESTSSL_IMAGE", DEFAULT_TESTSSL_IMAGE))
    parser.add_argument("--skip-testssl", action="store_true")
    parser.add_argument("--skip-pull", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=timeout_default)
    parser.add_argument("--print-report-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_scan(
        environment=args.env,
        receipt_dir=args.receipt_dir,
        artifacts_root=args.artifacts_root,
        testssl_image=args.testssl_image,
        pull_images=not args.skip_pull,
        skip_testssl=args.skip_testssl,
        timeout_seconds=args.timeout_seconds,
    )

    print(f"Receipt: {report['receipt_path']}")
    print(f"Targets: {report['summary']['target_count']}")
    print(f"Status: {report['summary']['status']}")
    if args.print_report_json:
        print(f"REPORT_JSON={json.dumps(report, separators=(',', ':'))}")
    _publish_receipt_to_outline(Path(report["receipt_path"]))
    return report["summary"]["status_code"]


def _publish_receipt_to_outline(receipt_path: Path) -> None:
    import subprocess
    import sys as _sys

    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = Path(__file__).resolve().parents[1] / ".local" / "outline" / "api-token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return
    outline_tool = Path(__file__).resolve().parent / "outline_tool.py"
    if not outline_tool.exists() or not receipt_path.exists():
        return
    try:
        subprocess.run(
            [_sys.executable, str(outline_tool), "receipt.publish", "--file", str(receipt_path)],
            capture_output=True,
            check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        raise SystemExit(emit_cli_error("https tls assurance", exc))
