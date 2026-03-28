#!/usr/bin/env python3
"""Validate Alertmanager rule files for ADR 0097 label and annotation requirements."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES_DIR = REPO_ROOT / "config" / "alertmanager" / "rules"
ALLOWED_SEVERITIES = {"critical", "warning", "info"}


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def load_rule_files(rules_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    payloads: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(rules_dir.glob("*.yml")):
        if path.name.startswith("._"):
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        payloads.append((path, require_mapping(document, str(path))))
    return payloads


def validate_rule_files(rules_dir: Path) -> list[str]:
    errors: list[str] = []
    for path, payload in load_rule_files(rules_dir):
        groups = payload.get("groups")
        if not isinstance(groups, list) or not groups:
            errors.append(f"{path}: missing non-empty groups list")
            continue
        for group_index, group in enumerate(groups):
            group = require_mapping(group, f"{path}.groups[{group_index}]")
            rules = group.get("rules")
            if not isinstance(rules, list) or not rules:
                errors.append(f"{path}: groups[{group_index}] missing non-empty rules list")
                continue
            for rule_index, rule in enumerate(rules):
                rule = require_mapping(rule, f"{path}.groups[{group_index}].rules[{rule_index}]")
                alert_name = rule.get("alert")
                if not isinstance(alert_name, str) or not alert_name:
                    continue
                labels = require_mapping(
                    rule.get("labels"), f"{path}.groups[{group_index}].rules[{rule_index}].labels"
                )
                annotations = require_mapping(
                    rule.get("annotations"),
                    f"{path}.groups[{group_index}].rules[{rule_index}].annotations",
                )
                severity = labels.get("severity")
                if severity not in ALLOWED_SEVERITIES:
                    errors.append(
                        f"{path}: alert {alert_name} must define labels.severity in {sorted(ALLOWED_SEVERITIES)}"
                    )
                if not isinstance(annotations.get("runbook_url"), str) or not annotations["runbook_url"].strip():
                    errors.append(f"{path}: alert {alert_name} is missing annotations.runbook_url")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules-dir", type=Path, default=DEFAULT_RULES_DIR)
    args = parser.parse_args(argv)

    errors = validate_rule_files(args.rules_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
