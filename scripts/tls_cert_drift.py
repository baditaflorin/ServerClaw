#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from typing import Any

from drift_lib import isoformat, utc_now
from tls_cert_probe import collect_certificate_results


def collect_drift(*, timeout_seconds: float = 5.0) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for result in collect_certificate_results(timeout_seconds=timeout_seconds, now=utc_now()):
        if result["severity"] == "ok":
            continue
        severity = "warn" if result["severity"] == "warning" else "critical"
        detail = result.get("error", "")
        if result["status"] == "issuer_mismatch":
            detail = f"issuer '{result['issuer']}' does not match expected provider {result['expected_issuer']}"
        elif "days_remaining" in result:
            detail = f"certificate expires in {result['days_remaining']} days"
        record = {
            "source": "tls",
            "event": f"platform.drift.{severity}",
            "severity": severity,
            "service": result["service_id"],
            "resource": result["certificate_id"],
            "detail": detail,
            "shared_surfaces": [result["service_id"], result["certificate_id"]],
        }
        if "issuer" in result:
            record["issuer"] = result["issuer"]
        if "expected_issuer" in result:
            record["expected_provider"] = result["expected_issuer"]
        if "not_after" in result:
            record["expires_at"] = result["not_after"]
        records.append(record)
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect TLS certificate expiry and issuer drift.")
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(collect_drift(timeout_seconds=args.timeout), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
