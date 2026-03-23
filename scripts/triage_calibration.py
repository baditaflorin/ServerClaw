#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, repo_path, write_json


DEFAULT_REPORT_DIR = repo_path(".local", "triage", "reports")
DEFAULT_CASES_PATH = repo_path(".local", "triage", "cases.jsonl")
DEFAULT_OUTPUT_PATH = repo_path(".local", "triage", "calibration", "latest.json")


def load_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON array")
        return [item for item in payload if isinstance(item, dict)]
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            result.append(item)
    return result


def load_reports(report_dir: Path) -> list[dict[str, Any]]:
    if not report_dir.exists():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            reports.append(payload)
    return reports


def calibrate(
    *,
    report_dir: Path = DEFAULT_REPORT_DIR,
    cases_path: Path | None = None,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    reports = load_reports(report_dir)
    cases = load_cases(cases_path or DEFAULT_CASES_PATH)
    case_by_incident = {
        case["incident_id"]: case
        for case in cases
        if isinstance(case.get("incident_id"), str) and case["incident_id"].strip()
    }

    per_rule: dict[str, dict[str, Any]] = {}
    matched_reports = 0
    cases_reviewed = 0
    for report in reports:
        incident_id = report.get("incident_id")
        case = case_by_incident.get(incident_id)
        hypotheses = report.get("hypotheses", [])
        top = hypotheses[0] if isinstance(hypotheses, list) and hypotheses else None
        if top is None:
            continue
        matched_reports += 1
        rule_id = top.get("id", "unknown")
        bucket = per_rule.setdefault(
            rule_id,
            {
                "rule_id": rule_id,
                "top_hypothesis_count": 0,
                "correct_top_hypothesis_count": 0,
                "resolved_case_count": 0,
                "precision": None,
                "recall": None,
            },
        )
        bucket["top_hypothesis_count"] += 1
        if not case:
            continue
        cases_reviewed += 1
        resolved_rule = case.get("resolved_rule_id")
        if isinstance(resolved_rule, str) and resolved_rule.strip():
            resolved_bucket = per_rule.setdefault(
                resolved_rule,
                {
                    "rule_id": resolved_rule,
                    "top_hypothesis_count": 0,
                    "correct_top_hypothesis_count": 0,
                    "resolved_case_count": 0,
                    "precision": None,
                    "recall": None,
                },
            )
            resolved_bucket["resolved_case_count"] += 1
        if resolved_rule == rule_id:
            bucket["correct_top_hypothesis_count"] += 1

    for bucket in per_rule.values():
        top_count = bucket["top_hypothesis_count"]
        resolved_count = bucket["resolved_case_count"]
        correct = bucket["correct_top_hypothesis_count"]
        bucket["precision"] = round(correct / top_count, 4) if top_count else None
        bucket["recall"] = round(correct / resolved_count, 4) if resolved_count else None

    status = "ok" if cases_reviewed else "insufficient_data"
    payload = {
        "status": status,
        "summary": {
            "reports_reviewed": len(reports),
            "reports_with_hypotheses": matched_reports,
            "cases_reviewed": cases_reviewed,
            "rules_with_data": sum(1 for bucket in per_rule.values() if bucket["top_hypothesis_count"] or bucket["resolved_case_count"]),
        },
        "rules": sorted(per_rule.values(), key=lambda item: item["rule_id"]),
        "output_path": str(output_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, payload, indent=2, sort_keys=True)
    return payload


def main() -> int:
    try:
        payload = calibrate()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("Triage calibration", exc)


if __name__ == "__main__":
    raise SystemExit(main())
