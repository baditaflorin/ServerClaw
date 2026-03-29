#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    override = os.environ.get("LV3_REPO_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


REPO_ROOT = repo_root()
CATALOG_PATH = REPO_ROOT / "config" / "replaceability-review-catalog.json"
ADR_DIR = REPO_ROOT / "docs" / "adr"

REQUIRED_SCORECARD_FIELDS = (
    "Capability Definition",
    "Contract Fit",
    "Data Export / Import",
    "Migration Complexity",
    "Proprietary Surface Area",
    "Approved Exceptions",
    "Fallback / Downgrade",
    "Observability / Audit Continuity",
)
REQUIRED_EXIT_PLAN_FIELDS = (
    "Reevaluation Triggers",
    "Portable Artifacts",
    "Migration Path",
    "Alternative Product",
    "Owner",
    "Review Cadence",
)
PLACEHOLDER_VALUES = {"todo", "tbd", "n/a", "not yet", "to be decided"}
SECTION_PATTERN = re.compile(
    r"^##\s+(?P<title>.+?)\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)
BULLET_PATTERN = re.compile(r"^\s*-\s+(?P<label>[^:]+):\s*(?P<value>.+?)\s*$", re.MULTILINE)
ADR_TITLE_PATTERN = re.compile(r"^#\s+ADR\s+(?P<adr>\d{4}):\s+(?P<title>.+)$", re.MULTILINE)
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class CriticalProductAdr:
    adr: str
    capability_id: str
    product_id: str
    critical_surface: str
    capability_definition_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReplaceabilityReport:
    adr: str
    title: str
    capability_id: str
    product_id: str
    owner: str
    review_cadence: str
    alternative_product: str


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_identifier(value: Any, path: str) -> str:
    value = _require_str(value, path)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", value):
        raise ValueError(f"{path} must use lowercase letters, numbers, and underscores")
    return value


def _require_adr_id(value: Any, path: str) -> str:
    value = _require_str(value, path)
    if not re.fullmatch(r"\d{4}", value):
        raise ValueError(f"{path} must be a four-digit ADR id")
    return value


def _require_semver(value: Any, path: str) -> str:
    value = _require_str(value, path)
    if not SEMVER_PATTERN.fullmatch(value):
        raise ValueError(f"{path} must use semantic version format")
    return value


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _resolve_repo_ref(ref: str) -> Path:
    file_ref = ref.split("#", 1)[0]
    path = REPO_ROOT / file_ref
    return path


def adr_path_for(adr: str) -> Path:
    matches = sorted(ADR_DIR.glob(f"{adr}-*.md"))
    if not matches:
        raise ValueError(f"missing ADR file for {adr} under {ADR_DIR}")
    return matches[0]


def load_replaceability_review_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_critical_product_adrs(catalog: dict[str, Any]) -> list[CriticalProductAdr]:
    entries = _require_list(catalog.get("critical_product_adrs"), "config/replaceability-review-catalog.json.critical_product_adrs")
    parsed: list[CriticalProductAdr] = []
    for index, entry in enumerate(entries):
        path = f"config/replaceability-review-catalog.json.critical_product_adrs[{index}]"
        entry = _require_mapping(entry, path)
        parsed.append(
            CriticalProductAdr(
                adr=_require_adr_id(entry.get("adr"), f"{path}.adr"),
                capability_id=_require_identifier(entry.get("capability_id"), f"{path}.capability_id"),
                product_id=_require_identifier(entry.get("product_id"), f"{path}.product_id"),
                critical_surface=_require_identifier(entry.get("critical_surface"), f"{path}.critical_surface"),
                capability_definition_refs=tuple(
                    _require_str(ref, f"{path}.capability_definition_refs[{ref_index}]")
                    for ref_index, ref in enumerate(
                        _require_list(entry.get("capability_definition_refs"), f"{path}.capability_definition_refs")
                    )
                ),
            )
        )
    return parsed


def validate_replaceability_review_catalog(catalog: dict[str, Any]) -> list[CriticalProductAdr]:
    catalog = _require_mapping(catalog, "config/replaceability-review-catalog.json")
    schema_ref = _require_str(catalog.get("$schema"), "config/replaceability-review-catalog.json.$schema")
    if schema_ref != "docs/schema/replaceability-review-catalog.schema.json":
        raise ValueError("config/replaceability-review-catalog.json.$schema must match the canonical schema path")
    _require_semver(catalog.get("schema_version"), "config/replaceability-review-catalog.json.schema_version")
    policy = _require_mapping(catalog.get("policy"), "config/replaceability-review-catalog.json.policy")
    policy_adr = _require_adr_id(policy.get("adr"), "config/replaceability-review-catalog.json.policy.adr")
    if policy_adr != "0212":
        raise ValueError("config/replaceability-review-catalog.json.policy.adr must reference ADR 0212")
    scope = _require_str(policy.get("scope"), "config/replaceability-review-catalog.json.policy.scope")
    if scope != "critical_integrated_product_adr":
        raise ValueError("config/replaceability-review-catalog.json.policy.scope must be critical_integrated_product_adr")
    notes = _require_list(policy.get("notes"), "config/replaceability-review-catalog.json.policy.notes")
    if not notes:
        raise ValueError("config/replaceability-review-catalog.json.policy.notes must not be empty")
    for index, note in enumerate(notes):
        _require_str(note, f"config/replaceability-review-catalog.json.policy.notes[{index}]")

    entries = parse_critical_product_adrs(catalog)
    if not entries:
        raise ValueError("config/replaceability-review-catalog.json.critical_product_adrs must not be empty")

    seen_adrs: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for entry in entries:
        if entry.adr in seen_adrs:
            raise ValueError(f"duplicate ADR {entry.adr} in config/replaceability-review-catalog.json")
        seen_adrs.add(entry.adr)
        pair = (entry.capability_id, entry.product_id)
        if pair in seen_pairs:
            raise ValueError(
                f"duplicate capability/product pair {entry.capability_id}/{entry.product_id} in config/replaceability-review-catalog.json"
            )
        seen_pairs.add(pair)

        adr_path = adr_path_for(entry.adr)
        if not adr_path.exists():
            raise ValueError(f"{adr_path} referenced by config/replaceability-review-catalog.json does not exist")
        for ref in entry.capability_definition_refs:
            resolved = _resolve_repo_ref(ref)
            if not resolved.exists():
                raise ValueError(
                    f"capability definition ref '{ref}' for ADR {entry.adr} does not resolve inside the repository"
                )
    return entries


def _extract_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for match in SECTION_PATTERN.finditer(text):
        sections[match.group("title").strip()] = match.group("body").strip()
    return sections


def _extract_labeled_bullets(section_body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in BULLET_PATTERN.finditer(section_body):
        label = match.group("label").strip()
        value = match.group("value").strip()
        fields[_normalize_label(label)] = value
    return fields


def _require_section_fields(
    *,
    adr_path: Path,
    section_title: str,
    section_body: str | None,
    required_labels: tuple[str, ...],
) -> dict[str, str]:
    if not section_body:
        raise ValueError(f"{adr_path.name} is missing required section '## {section_title}'")
    fields = _extract_labeled_bullets(section_body)
    for label in required_labels:
        normalized = _normalize_label(label)
        value = fields.get(normalized)
        if value is None:
            raise ValueError(f"{adr_path.name} is missing '{label}' in section '## {section_title}'")
        lowered = value.strip().lower()
        if lowered in PLACEHOLDER_VALUES or lowered.startswith("todo"):
            raise ValueError(
                f"{adr_path.name} has a placeholder value for '{label}' in section '## {section_title}'"
            )
    return fields


def validate_replaceability_sections(catalog: dict[str, Any]) -> list[ReplaceabilityReport]:
    entries = validate_replaceability_review_catalog(catalog)
    reports: list[ReplaceabilityReport] = []

    for entry in entries:
        adr_path = adr_path_for(entry.adr)
        text = adr_path.read_text(encoding="utf-8")
        title_match = ADR_TITLE_PATTERN.search(text)
        if not title_match:
            raise ValueError(f"{adr_path.name} must start with a canonical ADR heading")
        sections = _extract_sections(text)
        _require_section_fields(
            adr_path=adr_path,
            section_title="Replaceability Scorecard",
            section_body=sections.get("Replaceability Scorecard"),
            required_labels=REQUIRED_SCORECARD_FIELDS,
        )
        exit_fields = _require_section_fields(
            adr_path=adr_path,
            section_title="Vendor Exit Plan",
            section_body=sections.get("Vendor Exit Plan"),
            required_labels=REQUIRED_EXIT_PLAN_FIELDS,
        )
        reports.append(
            ReplaceabilityReport(
                adr=entry.adr,
                title=title_match.group("title").strip(),
                capability_id=entry.capability_id,
                product_id=entry.product_id,
                owner=exit_fields[_normalize_label("Owner")],
                review_cadence=exit_fields[_normalize_label("Review Cadence")],
                alternative_product=exit_fields[_normalize_label("Alternative Product")],
            )
        )
    return reports


def render_markdown_report(catalog: dict[str, Any]) -> str:
    reports = validate_replaceability_sections(catalog)
    lines = [
      "# Replaceability Review Coverage",
      "",
      "| ADR | Product | Capability | Owner | Review Cadence | Alternative Product |",
      "| --- | --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        lines.append(
            f"| `{report.adr}` | `{report.product_id}` | `{report.capability_id}` | {report.owner} | {report.review_cadence} | {report.alternative_product} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ADR 0212 replaceability scorecards and vendor exit plans.")
    parser.add_argument("--validate", action="store_true", help="Validate the replaceability review catalog and governed ADR sections.")
    parser.add_argument("--report", action="store_true", help="Print a Markdown summary of the governed replaceability reviews.")
    args = parser.parse_args(argv)

    if not args.validate and not args.report:
        parser.print_help()
        return 0

    try:
        catalog = load_replaceability_review_catalog()
        if args.validate:
            reports = validate_replaceability_sections(catalog)
            print(
                f"Replaceability scorecards OK: {len(reports)} governed ADRs "
                f"from {CATALOG_PATH.relative_to(REPO_ROOT)}"
            )
        if args.report:
            sys.stdout.write(render_markdown_report(catalog))
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"replaceability validation error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
