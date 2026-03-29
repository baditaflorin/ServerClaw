from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    if str(REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validation_lane_catalog_aligns_with_manifest() -> None:
    module = load_module("validation_lanes_catalog", "scripts/validation_lanes.py")
    manifest_checks = module.load_manifest_checks(REPO_ROOT / "config" / "validation-gate.json")
    catalog = module.load_catalog(
        catalog_path=REPO_ROOT / "config" / "validation-lanes.yaml",
        manifest_checks=manifest_checks,
    )

    assert "documentation-and-adr" in catalog.lanes
    assert catalog.fast_global_checks == ("workstream-surfaces", "agent-standards")


def test_docs_change_selects_docs_lane_without_remote_builder() -> None:
    module = load_module("validation_lanes_docs", "scripts/validation_lanes.py")
    manifest_checks = module.load_manifest_checks(REPO_ROOT / "config" / "validation-gate.json")
    catalog = module.load_catalog(
        catalog_path=REPO_ROOT / "config" / "validation-lanes.yaml",
        manifest_checks=manifest_checks,
    )

    selection = module.resolve_selection_from_changed_files(
        catalog,
        manifest_checks,
        changed_files=("docs/adr/0264-failure-domain-isolated-validation-lanes.md",),
        branch="codex/docs-only",
        base_ref="origin/main",
    )

    assert selection.selected_lanes == ("documentation-and-adr",)
    assert selection.blocking_checks == (
        "workstream-surfaces",
        "agent-standards",
        "documentation-index",
    )
    assert "remote-builder" not in selection.selected_lanes
    assert "security-scan" not in selection.blocking_checks


def test_unknown_surface_widens_to_all_lanes() -> None:
    module = load_module("validation_lanes_unknown", "scripts/validation_lanes.py")
    manifest_checks = module.load_manifest_checks(REPO_ROOT / "config" / "validation-gate.json")
    catalog = module.load_catalog(
        catalog_path=REPO_ROOT / "config" / "validation-lanes.yaml",
        manifest_checks=manifest_checks,
    )

    selection = module.resolve_selection_from_changed_files(
        catalog,
        manifest_checks,
        changed_files=("mystery/new-surface.txt",),
        branch="codex/unknown-surface",
        base_ref="origin/main",
    )

    assert selection.widened_to_all_lanes is True
    assert selection.unknown_files == ("mystery/new-surface.txt",)
    assert selection.selected_lanes == tuple(catalog.lanes)


def test_live_apply_receipt_change_stays_out_of_service_lane() -> None:
    module = load_module("validation_lanes_receipts", "scripts/validation_lanes.py")
    manifest_checks = module.load_manifest_checks(REPO_ROOT / "config" / "validation-gate.json")
    catalog = module.load_catalog(
        catalog_path=REPO_ROOT / "config" / "validation-lanes.yaml",
        manifest_checks=manifest_checks,
    )

    selection = module.resolve_selection_from_changed_files(
        catalog,
        manifest_checks,
        changed_files=("receipts/live-applies/2026-03-29-adr-0264-failure-domain-isolated-validation-lanes-mainline-live-apply.json",),
        branch="codex/receipt-only",
        base_ref="origin/main",
    )

    assert selection.widened_to_all_lanes is False
    assert selection.unknown_files == ()
    assert selection.selected_lanes == (
        "repository-structure-and-schema",
        "generated-artifact-and-canonical-truth",
    )
    assert "service-syntax-and-unit" not in selection.selected_lanes


def test_explicit_checks_keep_fast_global_invariants() -> None:
    module = load_module("validation_lanes_explicit", "scripts/validation_lanes.py")
    manifest_checks = module.load_manifest_checks(REPO_ROOT / "config" / "validation-gate.json")
    catalog = module.load_catalog(
        catalog_path=REPO_ROOT / "config" / "validation-lanes.yaml",
        manifest_checks=manifest_checks,
    )

    selection = module.resolve_selection_from_changed_files(
        catalog,
        manifest_checks,
        changed_files=(),
        branch="codex/explicit-checks",
        base_ref="origin/main",
        explicit_checks=("schema-validation",),
    )

    assert selection.mode == "explicit_checks"
    assert selection.blocking_checks == (
        "workstream-surfaces",
        "agent-standards",
        "schema-validation",
    )
    assert selection.selected_lanes == ("repository-structure-and-schema",)
