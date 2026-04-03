#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_ROOT = REPO_ROOT / "docs" / "discovery"
REPO_STRUCTURE_SOURCE_DIR = DISCOVERY_ROOT / "repo-structure"
CONFIG_LOCATIONS_SOURCE_DIR = DISCOVERY_ROOT / "config-locations"
PACK_MANIFEST_PATH = DISCOVERY_ROOT / "onboarding-packs.yaml"
REPO_STRUCTURE_OUTPUT = REPO_ROOT / ".repo-structure.yaml"
CONFIG_LOCATIONS_OUTPUT = REPO_ROOT / ".config-locations.yaml"
ONBOARDING_OUTPUT_DIR = REPO_ROOT / "build" / "onboarding"
GENERATOR_COMMAND = "uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --write"

REPO_QUICK_START = {
    "step_1": "Read README.md for current project status and merged deployment truth",
    "step_2": "Read AGENTS.md for working rules, conventions, and handoff protocol",
    "step_3": "Read this file (.repo-structure.yaml) for a concise section map",
    "step_4": "Read .config-locations.yaml to find the right config section",
    "step_5": "Read docs/adr/.index.yaml to search ADRs by keyword, concern, or reservation context",
    "step_6": "Check workstreams.yaml for active work and ownership contracts",
    "note": (
        "Use the section files under docs/discovery/ and the generated onboarding packs under "
        "build/onboarding/ when you need deeper task-specific discovery without loading every registry."
    ),
}

CONFIG_AGENT_QUICK_REFERENCE = {
    "find_config": "Read this file, then open the matching docs/discovery/config-locations/<section>.yaml source when you need deeper detail.",
    "where_to_document": {
        "infrastructure_changes": "workstreams.yaml + docs/workstreams/",
        "service_deployments": "versions/stack.yaml",
        "version_bumps": "VERSION + changelog.md + docs/release-notes/",
        "operational_changes": "receipts/live-applies/",
    },
    "source_of_truth": (
        "docs/discovery/config-locations/*.yaml is canonical; regenerate this root entrypoint and build/onboarding/* after edits."
    ),
    "validate": "./scripts/validate_repo.sh agent-standards generated-docs",
}

ENTRYPOINT_PURPOSES = {
    "README.md": "Current project status, merged platform truth, and fork-level orientation.",
    "AGENTS.md": "Working rules, handoff protocol, and collaboration conventions for agents.",
    ".repo-structure.yaml": "Generated root discovery entrypoint for repository layout and section navigation.",
    ".config-locations.yaml": "Generated root discovery entrypoint for canonical configuration locations.",
    "docs/adr/.index.yaml": "Generated ADR discovery index for keyword, concern, and reservation-aware queries.",
    "workstreams.yaml": "Active workstream registry plus ownership contracts and merge state.",
}

REPO_SECTION_ORDER = (
    "root-entrypoints",
    "documentation-and-history",
    "automation-and-infrastructure",
    "runtime-and-delivery",
    "cross-cutting-concerns",
)

CONFIG_SECTION_ORDER = (
    "agent-discovery",
    "project-tracking",
    "validation-and-ci",
    "infrastructure-state",
    "inventory",
    "automation",
    "service-configuration",
    "versioning",
)


class IndentedSafeDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False):  # type: ignore[override]
        return super().increase_indent(flow, False)


@dataclass(frozen=True)
class DiscoverySection:
    section_id: str
    title: str
    summary: str
    when_to_read: str
    entries: dict[str, Any]
    source_path: Path


@dataclass(frozen=True)
class PackDefinition:
    pack_id: str
    title: str
    summary: str
    root_entrypoints: tuple[str, ...]
    repo_structure_sections: tuple[str, ...]
    config_location_sections: tuple[str, ...]


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _require_mapping(payload, str(path))


def load_section_directory(source_dir: Path) -> list[DiscoverySection]:
    sections: list[DiscoverySection] = []
    seen_ids: set[str] = set()

    for path in sorted(source_dir.glob("*.yaml")):
        payload = _load_yaml(path)
        section_meta = _require_mapping(payload.get("section"), f"{path}.section")
        section_id = _require_string(section_meta.get("id"), f"{path}.section.id")
        if section_id in seen_ids:
            raise ValueError(f"duplicate discovery section id '{section_id}' in {source_dir}")
        seen_ids.add(section_id)
        entries = _require_mapping(payload.get("entries"), f"{path}.entries")
        sections.append(
            DiscoverySection(
                section_id=section_id,
                title=_require_string(section_meta.get("title"), f"{path}.section.title"),
                summary=_require_string(section_meta.get("summary"), f"{path}.section.summary"),
                when_to_read=_require_string(section_meta.get("when_to_read"), f"{path}.section.when_to_read"),
                entries=entries,
                source_path=path,
            )
        )

    if not sections:
        raise ValueError(f"no discovery sections found in {source_dir}")
    return sections


def load_pack_manifest(path: Path = PACK_MANIFEST_PATH) -> list[PackDefinition]:
    payload = _load_yaml(path)
    raw_packs = payload.get("packs")
    if not isinstance(raw_packs, list) or not raw_packs:
        raise ValueError(f"{path}.packs must be a non-empty list")

    packs: list[PackDefinition] = []
    seen_ids: set[str] = set()
    for index, raw_pack in enumerate(raw_packs):
        pack = _require_mapping(raw_pack, f"{path}.packs[{index}]")
        pack_id = _require_string(pack.get("id"), f"{path}.packs[{index}].id")
        if pack_id in seen_ids:
            raise ValueError(f"duplicate onboarding pack id '{pack_id}'")
        seen_ids.add(pack_id)
        root_entrypoints = tuple(
            _require_string(item, f"{path}.packs[{index}].root_entrypoints[{entry_index}]")
            for entry_index, item in enumerate(pack.get("root_entrypoints", []))
        )
        repo_sections = tuple(
            _require_string(item, f"{path}.packs[{index}].repo_structure_sections[{entry_index}]")
            for entry_index, item in enumerate(pack.get("repo_structure_sections", []))
        )
        config_sections = tuple(
            _require_string(item, f"{path}.packs[{index}].config_location_sections[{entry_index}]")
            for entry_index, item in enumerate(pack.get("config_location_sections", []))
        )
        packs.append(
            PackDefinition(
                pack_id=pack_id,
                title=_require_string(pack.get("title"), f"{path}.packs[{index}].title"),
                summary=_require_string(pack.get("summary"), f"{path}.packs[{index}].summary"),
                root_entrypoints=root_entrypoints,
                repo_structure_sections=repo_sections,
                config_location_sections=config_sections,
            )
        )
    return packs


def _section_by_id(sections: list[DiscoverySection]) -> dict[str, DiscoverySection]:
    return {section.section_id: section for section in sections}


def _entry_counts(section: DiscoverySection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in section.entries.items():
        if isinstance(value, dict):
            counts[key] = len(value)
    return counts


def _sort_sections(sections: list[DiscoverySection], preferred_order: tuple[str, ...]) -> list[DiscoverySection]:
    order_map = {section_id: index for index, section_id in enumerate(preferred_order)}
    return sorted(
        sections,
        key=lambda section: (order_map.get(section.section_id, len(order_map)), section.section_id),
    )


def _serialize_section(section: DiscoverySection) -> dict[str, Any]:
    return {
        "id": section.section_id,
        "title": section.title,
        "summary": section.summary,
        "when_to_read": section.when_to_read,
        "file": _relative(section.source_path),
        "entries": section.entries,
    }


def generated_date() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def build_repo_structure_root(
    repo_sections: list[DiscoverySection],
    packs: list[PackDefinition],
    *,
    generated_on: str,
) -> dict[str, Any]:
    ordered_sections = _sort_sections(repo_sections, REPO_SECTION_ORDER)
    return {
        "repository": "proxmox_reference_platform",
        "schema_version": 1,
        "generated": generated_on,
        "source_root": _relative(REPO_STRUCTURE_SOURCE_DIR),
        "pack_manifest": _relative(PACK_MANIFEST_PATH),
        "purpose": (
            "Generated root repository discovery entrypoint. Read this first for quick orientation, "
            "then open the deeper section files under docs/discovery/repo-structure/ when you need detail."
        ),
        "quick_start_for_agents": REPO_QUICK_START,
        "entrypoint_files": {path: ENTRYPOINT_PURPOSES[path] for path in ENTRYPOINT_PURPOSES},
        "section_index": [
            {
                "id": section.section_id,
                "title": section.title,
                "file": _relative(section.source_path),
                "summary": section.summary,
                "when_to_read": section.when_to_read,
                "entry_counts": _entry_counts(section),
            }
            for section in ordered_sections
        ],
        "onboarding_packs": [
            {
                "id": pack.pack_id,
                "title": pack.title,
                "file": f"build/onboarding/{pack.pack_id}.yaml",
                "summary": pack.summary,
            }
            for pack in packs
        ],
    }


def build_config_locations_root(
    config_sections: list[DiscoverySection],
    packs: list[PackDefinition],
    *,
    generated_on: str,
) -> dict[str, Any]:
    ordered_sections = _sort_sections(config_sections, CONFIG_SECTION_ORDER)
    return {
        "schema_version": 1,
        "generated": generated_on,
        "source_root": _relative(CONFIG_LOCATIONS_SOURCE_DIR),
        "pack_manifest": _relative(PACK_MANIFEST_PATH),
        "purpose": (
            "Generated root configuration discovery entrypoint. Use the section summaries below to choose "
            "the right canonical source file under docs/discovery/config-locations/."
        ),
        "agent_quick_reference": CONFIG_AGENT_QUICK_REFERENCE,
        "section_index": [
            {
                "id": section.section_id,
                "title": section.title,
                "file": _relative(section.source_path),
                "summary": section.summary,
                "when_to_read": section.when_to_read,
                "entry_count": len(section.entries),
            }
            for section in ordered_sections
        ],
        "onboarding_packs": [
            {
                "id": pack.pack_id,
                "title": pack.title,
                "file": f"build/onboarding/{pack.pack_id}.yaml",
                "summary": pack.summary,
            }
            for pack in packs
        ],
    }


def build_onboarding_pack(
    pack: PackDefinition,
    repo_section_map: dict[str, DiscoverySection],
    config_section_map: dict[str, DiscoverySection],
    *,
    generated_on: str,
) -> dict[str, Any]:
    missing_repo_sections = [section_id for section_id in pack.repo_structure_sections if section_id not in repo_section_map]
    missing_config_sections = [
        section_id for section_id in pack.config_location_sections if section_id not in config_section_map
    ]
    if missing_repo_sections or missing_config_sections:
        missing_parts = []
        if missing_repo_sections:
            missing_parts.append(f"repo_structure_sections={missing_repo_sections}")
        if missing_config_sections:
            missing_parts.append(f"config_location_sections={missing_config_sections}")
        raise ValueError(f"pack '{pack.pack_id}' references unknown sections: {', '.join(missing_parts)}")

    root_entrypoints: dict[str, str] = {}
    for entrypoint in pack.root_entrypoints:
        if entrypoint not in ENTRYPOINT_PURPOSES:
            raise ValueError(f"pack '{pack.pack_id}' references unknown root entrypoint '{entrypoint}'")
        root_entrypoints[entrypoint] = ENTRYPOINT_PURPOSES[entrypoint]

    repo_sections = [repo_section_map[section_id] for section_id in pack.repo_structure_sections]
    config_sections = [config_section_map[section_id] for section_id in pack.config_location_sections]

    generated_from = [
        _relative(PACK_MANIFEST_PATH),
        *(_relative(section.source_path) for section in repo_sections),
        *(_relative(section.source_path) for section in config_sections),
    ]

    return {
        "schema_version": 1,
        "generated": generated_on,
        "generated_from": generated_from,
        "pack": {
            "id": pack.pack_id,
            "title": pack.title,
            "summary": pack.summary,
        },
        "root_entrypoints": root_entrypoints,
        "repo_structure_sections": [_serialize_section(section) for section in repo_sections],
        "config_location_sections": [_serialize_section(section) for section in config_sections],
    }


def _render_yaml(payload: dict[str, Any]) -> str:
    return yaml.dump(
        payload,
        Dumper=IndentedSafeDumper,
        sort_keys=False,
        allow_unicode=False,
        width=1000,
    )


def _render_output(header_title: str, payload: dict[str, Any], write_hint: str) -> str:
    header = [
        "# ============================================================================",
        f"# {header_title}",
        "# ============================================================================",
        "# GENERATED FILE - do not edit by hand",
        f"# Regenerate: {write_hint}",
        "# ============================================================================",
        "",
    ]
    return "\n".join(header) + _render_yaml(payload)


def render_outputs() -> dict[Path, str]:
    repo_sections = load_section_directory(REPO_STRUCTURE_SOURCE_DIR)
    config_sections = load_section_directory(CONFIG_LOCATIONS_SOURCE_DIR)
    packs = load_pack_manifest()
    repo_section_map = _section_by_id(repo_sections)
    config_section_map = _section_by_id(config_sections)
    generated_on = generated_date()

    outputs: dict[Path, str] = {
        REPO_STRUCTURE_OUTPUT: _render_output(
            "Repository Structure Entry Point - ADR 0163 / ADR 0327",
            build_repo_structure_root(repo_sections, packs, generated_on=generated_on),
            GENERATOR_COMMAND,
        ),
        CONFIG_LOCATIONS_OUTPUT: _render_output(
            "Configuration Locations Entry Point - ADR 0166 / ADR 0327",
            build_config_locations_root(config_sections, packs, generated_on=generated_on),
            GENERATOR_COMMAND,
        ),
    }
    for pack in packs:
        outputs[ONBOARDING_OUTPUT_DIR / f"{pack.pack_id}.yaml"] = _render_output(
            f"Onboarding Pack - {pack.title}",
            build_onboarding_pack(pack, repo_section_map, config_section_map, generated_on=generated_on),
            GENERATOR_COMMAND,
        )
    return outputs


def write_outputs(outputs: dict[Path, str]) -> None:
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def check_outputs(outputs: dict[Path, str]) -> list[str]:
    stale: list[str] = []
    for path, expected in outputs.items():
        if not path.exists():
            stale.append(f"missing generated file: {_relative(path)}")
            continue
        current = path.read_text(encoding="utf-8")
        if current != expected:
            stale.append(f"stale generated file: {_relative(path)}")
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate ADR 0327 discovery entrypoints and onboarding packs."
    )
    parser.add_argument("--write", action="store_true", help="Write the generated outputs to disk.")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if generated outputs are stale.")
    args = parser.parse_args(argv)

    outputs = render_outputs()

    if args.check:
        stale = check_outputs(outputs)
        if stale:
            print("Discovery artifact generation is stale:", file=sys.stderr)
            for item in stale:
                print(f"- {item}", file=sys.stderr)
            return 1
        print("Discovery artifacts OK")
        return 0

    if args.write:
        write_outputs(outputs)
        for path in outputs:
            print(_relative(path))
        return 0

    for path, text in outputs.items():
        print(f"===== {_relative(path)} =====")
        print(text, end="" if text.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
