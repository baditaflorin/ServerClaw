from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

import workstream_surface_ownership as ownership


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_registry(*, include_manifest: bool = True) -> dict:
    workstream: dict[str, object] = {
        "id": "adr-0173-workstream-surface-ownership-manifest",
        "status": "ready",
        "branch": "codex/adr-0173-ownership-manifest",
        "doc": "/tmp/docs/workstreams/adr-0173.md",
    }
    if include_manifest:
        workstream["ownership_manifest"] = {
            "owned_surfaces": [
                {
                    "id": "workstream_registry",
                    "paths": ["workstreams.yaml"],
                    "mode": "shared_contract",
                    "contract": "workstream-registry-v1",
                },
                {
                    "id": "ownership_validator",
                    "paths": ["scripts/workstream_surface_ownership.py", "tests/test_workstream_surface_ownership.py"],
                    "mode": "exclusive",
                },
                {
                    "id": "integration_truth",
                    "paths": ["README.md", "VERSION"],
                    "mode": "generated",
                },
            ]
        }
    return {
        "delivery_model": {"registry_owner": "main"},
        "workstreams": [workstream],
    }


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Codex Test")
    git(repo, "config", "user.email", "codex@example.com")

    write(repo / "README.md", "# Test repo\n")
    write(repo / "scripts" / "workstream_surface_ownership.py", "print('stub')\n")
    write(repo / "tests" / "test_workstream_surface_ownership.py", "def test_stub():\n    assert True\n")
    write(repo / "docs" / "workstreams" / "adr-0173.md", "# doc\n")
    write(repo / "workstreams.yaml", yaml.safe_dump(build_registry(), sort_keys=False))

    git(repo, "add", ".")
    git(repo, "commit", "-m", "Initial")
    git(repo, "checkout", "-b", "codex/adr-0173-ownership-manifest")
    return repo


def test_validate_registry_requires_manifest_for_active_workstream() -> None:
    registry = build_registry(include_manifest=False)

    with pytest.raises(ValueError, match="ownership_manifest is required"):
        ownership.validate_registry(registry)


def test_validate_registry_rejects_duplicate_exclusive_surface_across_active_workstreams() -> None:
    registry = build_registry()
    registry["workstreams"].append(
        {
            "id": "adr-9999-another",
            "status": "implemented",
            "branch": "codex/adr-9999-another",
            "doc": "/tmp/docs/workstreams/adr-9999.md",
            "ownership_manifest": {
                "owned_surfaces": [
                    {
                        "id": "ownership_validator",
                        "paths": ["scripts/other.py"],
                        "mode": "exclusive",
                    }
                ]
            },
        }
    )

    with pytest.raises(ValueError, match="claimed as exclusive"):
        ownership.validate_registry(registry)


def test_validate_registry_rejects_shared_contract_mismatch() -> None:
    registry = build_registry()
    registry["workstreams"].append(
        {
            "id": "adr-9999-another",
            "status": "ready",
            "branch": "codex/adr-9999-another",
            "doc": "/tmp/docs/workstreams/adr-9999.md",
            "ownership_manifest": {
                "owned_surfaces": [
                    {
                        "id": "workstream_registry",
                        "paths": ["workstreams.yaml"],
                        "mode": "shared_contract",
                        "contract": "workstream-registry-v2",
                    }
                ]
            },
        }
    )

    with pytest.raises(ValueError, match="must use a single contract"):
        ownership.validate_registry(registry)


def test_validate_branch_allows_declared_mutable_surfaces(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    write(repo / "scripts" / "workstream_surface_ownership.py", "print('changed')\n")
    write(repo / "workstreams.yaml", yaml.safe_dump(build_registry(), sort_keys=False))

    changed_files = ownership.validate_branch_ownership(repo_root=repo, base_ref="main")

    assert changed_files == ["scripts/workstream_surface_ownership.py"]


def test_validate_branch_rejects_generated_surface_edits(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    write(repo / "README.md", "# changed\n")

    with pytest.raises(ValueError, match="direct edits are not allowed"):
        ownership.validate_branch_ownership(repo_root=repo, base_ref="main")


def test_validate_branch_rejects_undeclared_paths(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    write(repo / "notes.txt", "hello\n")

    with pytest.raises(ValueError, match="outside declared owned surfaces"):
        ownership.validate_branch_ownership(repo_root=repo, base_ref="main")


def test_validate_branch_uses_snapshot_env_without_git_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    write(repo / "scripts" / "workstream_surface_ownership.py", "print('changed')\n")
    write(repo / "docs" / "workstreams" / "adr-0173.md", "# doc\n")
    write(repo / "workstreams.yaml", yaml.safe_dump(build_registry(), sort_keys=False))

    monkeypatch.setenv("LV3_SNAPSHOT_BRANCH", "codex/adr-0173-ownership-manifest")
    monkeypatch.setenv(
        "LV3_VALIDATION_CHANGED_FILES_JSON",
        '["scripts/workstream_surface_ownership.py"]',
    )

    changed_files = ownership.validate_branch_ownership(repo_root=repo)

    assert changed_files == ["scripts/workstream_surface_ownership.py"]
