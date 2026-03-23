#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


DEFAULT_SUPPRESSIONS_PATH = repo_path("config", "lynis-suppressions.json")
FINDING_ID_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d{2,5})\b")


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def load_suppressions(path: Path = DEFAULT_SUPPRESSIONS_PATH) -> dict[str, dict[str, Any]]:
    payload = load_json(path, default={"schema_version": "1.0.0", "suppressions": []})
    payload = require_mapping(payload, str(path))
    suppressions = payload.get("suppressions", [])
    result: dict[str, dict[str, Any]] = {}
    if isinstance(suppressions, dict):
        for finding_id, metadata in suppressions.items():
            result[str(finding_id)] = metadata if isinstance(metadata, dict) else {}
        return result
    if not isinstance(suppressions, list):
        raise ValueError(f"{path}.suppressions must be a list or object")
    for index, item in enumerate(suppressions):
        item = require_mapping(item, f"{path}.suppressions[{index}]")
        finding_id = item.get("id")
        if not isinstance(finding_id, str) or not finding_id:
            raise ValueError(f"{path}.suppressions[{index}].id must be a non-empty string")
        result[finding_id] = item
    return result


def parse_kv_lines(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    scalar_values: dict[str, str] = {}
    list_values: dict[str, list[str]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key.endswith("[]"):
            list_values.setdefault(key[:-2], []).append(value)
            continue
        scalar_values[key] = value
    return scalar_values, list_values


def extract_hardening_index(values: dict[str, str]) -> int | None:
    for key in ("hardening_index", "hardening-index", "hardeningindex"):
        value = values.get(key)
        if value and value.isdigit():
            return int(value)
    for candidate in values.values():
        match = re.search(r"\b(\d{1,3})\b", candidate)
        if match:
            score = int(match.group(1))
            if 0 <= score <= 100:
                return score
    return None


def normalize_entry(entry: str) -> list[str]:
    for separator in ("|", ";", "::"):
        if separator in entry:
            return [part.strip() for part in entry.split(separator) if part.strip()]
    return [entry.strip()]


def parse_finding_entry(entry: str, finding_type: str, suppressions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    parts = normalize_entry(entry)
    match = FINDING_ID_PATTERN.search(parts[0] if parts else entry)
    finding_id = match.group(1) if match else "UNKNOWN"
    description = parts[1] if len(parts) > 1 else entry
    if match:
        description = description.replace(match.group(1), "", 1).strip(" :-")
    finding: dict[str, Any] = {
        "id": finding_id,
        "type": finding_type,
        "description": description or entry,
        "suggestion": parts[2] if len(parts) > 2 else "",
        "raw": entry,
    }
    if finding_id in suppressions:
        finding["suppressed"] = True
        finding["suppression"] = suppressions[finding_id]
    else:
        finding["suppressed"] = False
    return finding


def parse_report_text(
    text: str,
    *,
    host: str | None = None,
    suppressions: dict[str, dict[str, Any]] | None = None,
    include_suppressed: bool = False,
) -> dict[str, Any]:
    suppressions = suppressions or {}
    scalar_values, list_values = parse_kv_lines(text)
    resolved_host = host or scalar_values.get("hostname") or scalar_values.get("host") or "unknown"
    hardening_index = extract_hardening_index(scalar_values)

    findings = [
        parse_finding_entry(entry, "warning", suppressions)
        for entry in list_values.get("warning", [])
    ] + [
        parse_finding_entry(entry, "suggestion", suppressions)
        for entry in list_values.get("suggestion", [])
    ]

    visible_findings = findings if include_suppressed else [item for item in findings if not item["suppressed"]]
    warning_count = sum(1 for item in visible_findings if item["type"] == "warning")
    suggestion_count = sum(1 for item in visible_findings if item["type"] == "suggestion")

    return {
        "host": resolved_host,
        "hardening_index": hardening_index,
        "finding_counts": {
          "warning": warning_count,
          "suggestion": suggestion_count,
          "suppressed": sum(1 for item in findings if item["suppressed"]),
        },
        "findings": visible_findings,
        "suppressed_findings": [item for item in findings if item["suppressed"]],
        "raw_keys": sorted(scalar_values.keys()),
    }


def parse_path(
    path: Path,
    *,
    suppressions: dict[str, dict[str, Any]],
    include_suppressed: bool,
    host_override: str | None = None,
) -> list[dict[str, Any]]:
    if path.is_dir():
        results: list[dict[str, Any]] = []
        for child in sorted(path.glob("*.dat")):
            results.extend(
                parse_path(
                    child,
                    suppressions=suppressions,
                    include_suppressed=include_suppressed,
                )
            )
        return results

    report_host = host_override
    if report_host is None:
        stem = path.stem
        report_host = stem.removesuffix("-lynis-report")
    return [
        parse_report_text(
            path.read_text(encoding="utf-8"),
            host=report_host,
            suppressions=suppressions,
            include_suppressed=include_suppressed,
        )
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse one or more Lynis report.dat files into JSON.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--host", help="Override the host name for a single input file.")
    parser.add_argument("--suppressions", type=Path, default=DEFAULT_SUPPRESSIONS_PATH)
    parser.add_argument("--include-suppressed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        suppressions = load_suppressions(args.suppressions)
        reports: list[dict[str, Any]] = []
        for path in args.paths:
            reports.extend(
                parse_path(
                    path,
                    suppressions=suppressions,
                    include_suppressed=args.include_suppressed,
                    host_override=args.host if len(args.paths) == 1 else None,
                )
            )
        print(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("parse_lynis_report", exc)


if __name__ == "__main__":
    raise SystemExit(main())
