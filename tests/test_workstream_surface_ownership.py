from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

import workstream_surface_ownership as ownership
from platform.workstream_registry import write_assembled_registry, write_workstream


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_registry(*, include_manifest: bool = True) -> dict:
    workstream: dict[str, object] = {
        "id": "adr-0173-workstream-surface-ownership-manifest",
        "status": "ready",
        "branch": "codex/adr-0173-ownership-manifest",
        "doc": "docs/workstreams/adr-0173.md",
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


def init_closeout_repo(tmp_path: Path) -> Path:
    repo = init_repo(tmp_path)
    git(repo, "checkout", "main")

    registry = build_registry()
    workstream = registry["workstreams"][0]
    workstream["status"] = "ready_for_merge"
    policy = {
        "schema_version": "1.0.0",
        "delivery_model": registry["delivery_model"],
        "release_policy": {"breaking_change_criteria": "config/version-semantics.json"},
        "surface_ownership": {"global_mutable_paths": ["workstreams.yaml"]},
    }
    write(repo / "workstreams" / "policy.yaml", yaml.safe_dump(policy, sort_keys=False))
    (repo / "workstreams" / "archive").mkdir(parents=True, exist_ok=True)
    active_path = repo / "workstreams" / "active" / f"{workstream['id']}.yaml"
    write(active_path, yaml.safe_dump(workstream, sort_keys=False))
    write_assembled_registry(repo_root=repo)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Register source workstream before closeout")
    git(repo, "checkout", "-b", "codex/adr-0173-closeout")

    workstream["branch"] = "codex/adr-0173-closeout"
    workstream["status"] = "merged"
    workstream["ready_to_merge"] = False
    write_workstream(workstream, repo_root=repo, current_path=active_path, archive_year="2026")
    write_assembled_registry(repo_root=repo)
    return repo


def test_validate_registry_requires_manifest_for_active_workstream() -> None:
    registry = build_registry(include_manifest=False)

    with pytest.raises(ValueError, match="ownership_manifest is required"):
        ownership.validate_registry(registry)


def test_parse_archive_implemented_workstream_as_terminal_without_manifest() -> None:
    registry = build_registry(include_manifest=False)
    registry["workstreams"][0]["status"] = "implemented"

    parsed = ownership.parse_workstream_ownerships(registry)

    assert parsed[0].is_active is False


def test_validate_registry_rejects_duplicate_exclusive_surface_across_active_workstreams() -> None:
    registry = build_registry()
    registry["workstreams"].append(
        {
            "id": "adr-9999-another",
            "status": "in_progress",
            "branch": "codex/adr-9999-another",
            "doc": "docs/workstreams/adr-9999.md",
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
            "doc": "docs/workstreams/adr-9999.md",
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


def test_validate_registry_rejects_parent_relative_metadata() -> None:
    registry = build_registry()
    registry["workstreams"][0]["doc"] = "../docs/workstreams/adr-0173.md"
    registry["workstreams"][0]["worktree_path"] = "../outside"

    with pytest.raises(ValueError, match="must stay within the repository root"):
        ownership.validate_registry(registry)


def test_validate_registry_rejects_workstream_path_escape() -> None:
    registry = build_registry()
    registry["workstreams"][0]["doc"] = "../outside-repo/docs/workstreams/adr-0173.md"

    with pytest.raises(ValueError, match="must stay within the repository root"):
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


def test_validate_branch_allows_terminal_workstream_with_manifest(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    registry = build_registry()
    registry["workstreams"][0]["status"] = "live_applied"
    write(repo / "scripts" / "workstream_surface_ownership.py", "print('changed')\n")
    write(repo / "workstreams.yaml", yaml.safe_dump(registry, sort_keys=False))

    changed_files = ownership.validate_branch_ownership(repo_root=repo, base_ref="main")

    assert changed_files == ["scripts/workstream_surface_ownership.py", "workstreams.yaml"]


def test_validate_branch_allows_editing_its_own_workstream_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = init_repo(tmp_path)
    registry = build_registry()
    write(
        repo / "workstreams" / "policy.yaml",
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "delivery_model": registry["delivery_model"],
                "release_policy": {"breaking_change_criteria": "config/version-semantics.json"},
            },
            sort_keys=False,
        ),
    )
    (repo / "workstreams" / "archive").mkdir(parents=True, exist_ok=True)
    shard_path = repo / "workstreams" / "active" / "adr-0173-workstream-surface-ownership-manifest.yaml"
    write(shard_path, yaml.safe_dump(registry["workstreams"][0], sort_keys=False))
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Add shard source")

    write(shard_path, yaml.safe_dump(registry["workstreams"][0], sort_keys=False).replace("ready", "in_progress", 1))
    monkeypatch.setenv(
        "LV3_VALIDATION_CHANGED_FILES_JSON",
        '["workstreams/active/adr-0173-workstream-surface-ownership-manifest.yaml"]',
    )

    changed_files = ownership.validate_branch_ownership(repo_root=repo, base_ref="main")

    assert changed_files == ["workstreams/active/adr-0173-workstream-surface-ownership-manifest.yaml"]


def test_validate_branch_resolves_archived_record_after_it_leaves_compatibility_registry(
    tmp_path: Path,
) -> None:
    repo = init_closeout_repo(tmp_path)

    changed_files = ownership.validate_branch_ownership(repo_root=repo, base_ref="main")

    assert changed_files == [
        "workstreams.yaml",
        "workstreams/active/adr-0173-workstream-surface-ownership-manifest.yaml",
        "workstreams/archive/2026/adr-0173-workstream-surface-ownership-manifest.yaml",
    ]


def test_validate_archiving_branch_still_rejects_unowned_edits(tmp_path: Path) -> None:
    repo = init_closeout_repo(tmp_path)
    write(repo / "notes.txt", "unrelated change\n")

    with pytest.raises(ValueError, match="outside declared owned surfaces"):
        ownership.validate_branch_ownership(repo_root=repo, base_ref="main")
