from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.use_cases.serverclaw_skills import (  # noqa: E402
    list_serverclaw_skill_packs,
    validate_serverclaw_skill_pack_repository,
)


def test_workspace_skill_pack_override_wins_over_bundled_default() -> None:
    payload = list_serverclaw_skill_packs(workspace_id="ops", include_prompt_manifest=True)

    active = {entry["skill_id"]: entry for entry in payload["active_skills"]}
    assert active["platform-observe"]["source_tier"] == "workspace"
    assert active["change-approval"]["source_tier"] == "shared"

    assert {
        "skill_id": "platform-observe",
        "active_source_tier": "workspace",
        "shadowed_source_tier": "bundled",
        "shadowed_source_path": "config/serverclaw/skills/bundled/platform-observe/SKILL.md",
    } in payload["shadowed_skills"]

    assert any(entry["skill_id"] == "platform-observe" for entry in payload["prompt_manifest"])


def test_requested_skill_filters_the_active_catalog() -> None:
    payload = list_serverclaw_skill_packs(workspace_id="ops", skill_id="platform-observe")

    assert payload["active_skill_count"] == 1
    assert [entry["skill_id"] for entry in payload["active_skills"]] == ["platform-observe"]


def test_repository_contract_reports_active_and_imported_skill_counts() -> None:
    summary = validate_serverclaw_skill_pack_repository()

    assert summary["default_workspace_id"] == "ops"
    assert summary["workspace_ids"] == ["ops"]
    assert summary["active_skill_count"] == 2
    assert summary["imported_skill_count"] == 1
