from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_required_entrypoints(root: Path) -> None:
    (root / "docs" / "release-notes").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "discovery" / "repo-structure").mkdir(parents=True, exist_ok=True)
    (root / "build" / "onboarding").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("generic readme\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("generic agents\n", encoding="utf-8")
    (root / ".repo-structure.yaml").write_text("sections: []\n", encoding="utf-8")
    (root / ".config-locations.yaml").write_text("sections: []\n", encoding="utf-8")
    (root / "changelog.md").write_text("# Changelog\n", encoding="utf-8")
    (root / "docs" / "release-notes" / "README.md").write_text("# Releases\n", encoding="utf-8")
    (root / "workstreams.yaml").write_text(
        yaml.safe_dump({"delivery_model": {}, "release_policy": {}, "workstreams": []}, sort_keys=False),
        encoding="utf-8",
    )


def test_validate_public_entrypoints_scans_discovery_source_files(tmp_path: Path) -> None:
    module = load_module("validate_public_entrypoints_discovery", "scripts/validate_public_entrypoints.py")
    _write_required_entrypoints(tmp_path)
    (tmp_path / "docs" / "discovery" / "repo-structure" / "root-entrypoints.yaml").write_text(
        "path: /Users/tester/private/file\n",
        encoding="utf-8",
    )

    module.REPO_ROOT = tmp_path
    findings = module.validate_public_entrypoints()

    assert any("docs/discovery/repo-structure/root-entrypoints.yaml" in finding for finding in findings)
    assert any("macOS home path" in finding for finding in findings)


def test_validate_public_entrypoints_scans_generated_onboarding_packs(tmp_path: Path) -> None:
    module = load_module("validate_public_entrypoints_onboarding", "scripts/validate_public_entrypoints.py")
    _write_required_entrypoints(tmp_path)
    (tmp_path / "build" / "onboarding" / "agent-core.yaml").write_text(
        "hostname: proxmox-host\n",
        encoding="utf-8",
    )

    module.REPO_ROOT = tmp_path
    findings = module.validate_public_entrypoints()

    assert any("build/onboarding/agent-core.yaml" in finding for finding in findings)
    assert any("deployment-specific hostname label" in finding for finding in findings)


def test_validate_public_entrypoints_rejects_parent_relative_workstream_metadata(tmp_path: Path) -> None:
    module = load_module("validate_public_entrypoints_workstreams", "scripts/validate_public_entrypoints.py")
    _write_required_entrypoints(tmp_path)
    (tmp_path / "workstreams.yaml").write_text(
        yaml.safe_dump(
            {
                "delivery_model": {"workstream_doc_root": "docs/workstreams"},
                "release_policy": {"breaking_change_criteria": "config/version-semantics.json"},
                "workstreams": [
                    {
                        "id": "ws-1000-test",
                        "worktree_path": "../outside",
                        "doc": "../outside/docs/workstreams/ws-1000-test.md",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    module.REPO_ROOT = tmp_path
    findings = module.validate_public_entrypoints()

    assert any("worktree_path must stay within the repository root" in finding for finding in findings)
    assert any("doc must stay within the repository root" in finding for finding in findings)


def test_validate_public_entrypoints_rejects_workstream_path_escapes(tmp_path: Path) -> None:
    module = load_module("validate_public_entrypoints_paths", "scripts/validate_public_entrypoints.py")
    _write_required_entrypoints(tmp_path)
    (tmp_path / "workstreams.yaml").write_text(
        yaml.safe_dump(
            {
                "delivery_model": {"workstream_doc_root": "docs/workstreams"},
                "release_policy": {"breaking_change_criteria": "config/version-semantics.json"},
                "workstreams": [
                    {
                        "id": "ws-0337-live-apply",
                        "worktree_path": "../outside-repo",
                        "doc": "../outside-repo/docs/workstreams/ws-0337-live-apply.md",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    module.REPO_ROOT = tmp_path
    findings = module.validate_public_entrypoints()

    assert "workstreams.yaml: workstreams[0].worktree_path must stay within the repository root" in findings
    assert "workstreams.yaml: workstreams[0].doc must stay within the repository root" in findings
