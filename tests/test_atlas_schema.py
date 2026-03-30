from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "atlas_schema.py"


def load_module():
    spec = importlib.util.spec_from_file_location("atlas_schema", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_catalog_accepts_repo_catalog() -> None:
    atlas_schema = load_module()
    catalog_path = REPO_ROOT / "config" / "atlas" / "catalog.json"

    catalog = atlas_schema.load_catalog(catalog_path)
    atlas_schema.validate_catalog(catalog, repo_root=REPO_ROOT)

    assert catalog["schema_version"] == "1.0.0"
    assert len(catalog["databases"]) >= 20
    assert catalog["openbao"]["database_role"] == "postgres-atlas-readonly"


def test_select_lint_targets_skips_when_changed_files_are_unrelated() -> None:
    atlas_schema = load_module()
    catalog = atlas_schema.load_catalog(REPO_ROOT / "config" / "atlas" / "catalog.json")

    selected = atlas_schema.select_lint_targets(
        catalog,
        changed_files=("docs/runbooks/configure-openbao.md",),
        explicit_target_ids=(),
    )

    assert selected == []


def test_select_lint_targets_includes_migration_changes() -> None:
    atlas_schema = load_module()
    catalog = atlas_schema.load_catalog(REPO_ROOT / "config" / "atlas" / "catalog.json")

    selected = atlas_schema.select_lint_targets(
        catalog,
        changed_files=("migrations/0017_serverclaw_memory_schema.sql",),
        explicit_target_ids=(),
    )

    assert [target["id"] for target in selected] == ["platform-control-plane"]


def test_parse_changed_files_reads_validation_environment(monkeypatch) -> None:
    atlas_schema = load_module()
    monkeypatch.setenv(
        "LV3_VALIDATION_CHANGED_FILES_JSON",
        json.dumps(["migrations/0010_world_state_schema.sql", "config/atlas/catalog.json"]),
    )

    assert atlas_schema.parse_changed_files() == (
        "migrations/0010_world_state_schema.sql",
        "config/atlas/catalog.json",
    )


def test_diff_preview_is_bounded() -> None:
    atlas_schema = load_module()
    left = "\n".join(f"left-{index}" for index in range(260))
    right = "\n".join(f"right-{index}" for index in range(260))

    preview = atlas_schema.diff_preview(left, right, label="windmill")

    assert preview[0].startswith("--- windmill-snapshot")
    assert preview[-1] == "... diff truncated ..."
    assert len(preview) == 201
