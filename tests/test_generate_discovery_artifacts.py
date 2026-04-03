from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_discovery_artifacts as generator  # noqa: E402


def _load_generated_yaml(text: str) -> dict:
    payload_lines = [line for line in text.splitlines() if not line.startswith("#")]
    return yaml.safe_load("\n".join(payload_lines))


def test_render_outputs_include_section_indexes_and_pack_targets() -> None:
    outputs = generator.render_outputs()

    repo_root_text = outputs[generator.REPO_STRUCTURE_OUTPUT]
    config_root_text = outputs[generator.CONFIG_LOCATIONS_OUTPUT]

    assert "docs/discovery/repo-structure/root-entrypoints.yaml" in repo_root_text
    assert "docs/discovery/repo-structure/documentation-and-history.yaml" in repo_root_text
    assert "build/onboarding/agent-core.yaml" in repo_root_text

    assert "docs/discovery/config-locations/agent-discovery.yaml" in config_root_text
    assert "docs/discovery/config-locations/validation-and-ci.yaml" in config_root_text
    assert "build/onboarding/service-catalog.yaml" in config_root_text


def test_generated_service_catalog_pack_contains_selected_sections() -> None:
    outputs = generator.render_outputs()
    payload = _load_generated_yaml(outputs[generator.ONBOARDING_OUTPUT_DIR / "service-catalog.yaml"])

    assert payload["pack"]["id"] == "service-catalog"
    assert [section["id"] for section in payload["repo_structure_sections"]] == [
        "automation-and-infrastructure",
        "documentation-and-history",
        "runtime-and-delivery",
    ]
    assert [section["id"] for section in payload["config_location_sections"]] == [
        "infrastructure-state",
        "inventory",
        "service-configuration",
        "automation",
    ]
    assert "docs/discovery/config-locations/service-configuration.yaml" in payload["generated_from"]
    assert payload["root_entrypoints"][".config-locations.yaml"].startswith("Generated root discovery entrypoint")


def test_generated_root_outputs_keep_concise_section_summaries() -> None:
    outputs = generator.render_outputs()
    payload = _load_generated_yaml(outputs[generator.REPO_STRUCTURE_OUTPUT])

    assert payload["repository"] == "proxmox_reference_platform"
    assert len(payload["section_index"]) == 5
    assert payload["section_index"][0]["id"] == "root-entrypoints"
    assert payload["section_index"][0]["entry_counts"]["top_level_files"] >= 6
    assert payload["onboarding_packs"][0]["id"] == "agent-core"


def test_render_outputs_use_one_utc_generated_date(monkeypatch) -> None:
    monkeypatch.setattr(generator, "generated_date", lambda: dt.date(2026, 4, 3).isoformat())

    outputs = generator.render_outputs()

    repo_payload = _load_generated_yaml(outputs[generator.REPO_STRUCTURE_OUTPUT])
    config_payload = _load_generated_yaml(outputs[generator.CONFIG_LOCATIONS_OUTPUT])
    pack_payload = _load_generated_yaml(outputs[generator.ONBOARDING_OUTPUT_DIR / "agent-core.yaml"])

    assert repo_payload["generated"] == "2026-04-03"
    assert config_payload["generated"] == "2026-04-03"
    assert pack_payload["generated"] == "2026-04-03"
