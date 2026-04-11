#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from collections.abc import Iterable


ALLOWED_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"}
REQUIRED_FIELDS = ("ts", "level", "service_id", "component", "trace_id", "msg", "vm")


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str | None = None
    service_id: str | None = None
    line: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "service_id": self.service_id,
            "line": self.line,
        }


def _coerce_line(raw_line: str) -> str:
    stripped = raw_line.strip()
    if not stripped:
        return ""
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(payload, dict) and isinstance(payload.get("log"), str):
        return payload["log"].strip()
    return stripped


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_line(raw_line: str) -> ValidationResult:
    line = _coerce_line(raw_line)
    if not line:
        return ValidationResult(valid=True)

    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return ValidationResult(valid=False, reason="not_json", line=line[:240])
    if not isinstance(payload, dict):
        return ValidationResult(valid=False, reason="not_object", line=line[:240])

    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        return ValidationResult(
            valid=False,
            reason="missing_fields:" + ",".join(missing),
            service_id=str(payload.get("service_id") or "unknown"),
            line=line[:240],
        )

    for field in ("service_id", "component", "trace_id", "msg", "vm"):
        if not _is_non_empty_string(payload.get(field)):
            return ValidationResult(
                valid=False,
                reason=f"invalid_{field}",
                service_id=str(payload.get("service_id") or "unknown"),
                line=line[:240],
            )

    level = payload.get("level")
    if not _is_non_empty_string(level) or str(level).upper() not in ALLOWED_LEVELS:
        return ValidationResult(
            valid=False,
            reason="invalid_level",
            service_id=str(payload.get("service_id") or "unknown"),
            line=line[:240],
        )

    timestamp = payload.get("ts")
    if not _is_non_empty_string(timestamp):
        return ValidationResult(
            valid=False,
            reason="invalid_ts",
            service_id=str(payload.get("service_id") or "unknown"),
            line=line[:240],
        )
    try:
        datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return ValidationResult(
            valid=False,
            reason="invalid_ts",
            service_id=str(payload.get("service_id") or "unknown"),
            line=line[:240],
        )

    return ValidationResult(valid=True, service_id=str(payload.get("service_id")))


def iter_lines(path: Path | None) -> Iterable[str]:
    if path is None:
        yield from sys.stdin
        return
    yield from path.read_text(encoding="utf-8").splitlines()


def summarize(results: list[ValidationResult]) -> dict[str, Any]:
    violations = [result.as_dict() for result in results if not result.valid]
    service_counts: dict[str, int] = {}
    for item in violations:
        service_id = str(item.get("service_id") or "unknown")
        service_counts[service_id] = service_counts.get(service_id, 0) + 1
    return {
        "valid": not violations,
        "checked_lines": len(results),
        "violation_count": len(violations),
        "violations_by_service": service_counts,
        "violations": violations,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate LV3 structured log lines.")
    parser.add_argument("path", nargs="?", type=Path, help="Optional log file to validate. Reads stdin when omitted.")
    parser.add_argument("--report-json", action="store_true", help="Print the validation summary as JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = [validate_line(line) for line in iter_lines(args.path)]
    summary = summarize(results)
    if args.report_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            f"checked={summary['checked_lines']} valid={'yes' if summary['valid'] else 'no'} "
            f"violations={summary['violation_count']}"
        )
        for item in summary["violations"]:
            print(f"{item['service_id']}: {item['reason']}")
    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
