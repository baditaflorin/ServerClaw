from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import control_metadata_witness as witness


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    remote_root = tmp_path / "origin.git"
    repo_root.mkdir()
    remote_root.mkdir()
    assert git(repo_root, "init", "-b", "main").returncode == 0
    assert git(repo_root, "config", "user.name", "Codex").returncode == 0
    assert git(repo_root, "config", "user.email", "codex@example.com").returncode == 0
    assert git(remote_root, "init", "--bare").returncode == 0
    assert git(repo_root, "remote", "add", "origin", str(remote_root)).returncode == 0

    write(repo_root / "VERSION", "0.176.0\n")
    write(repo_root / "README.md", "# Test Repo\n")
    write(repo_root / "changelog.md", "# Changelog\n")
    write(repo_root / "workstreams.yaml", "workstreams: []\n")
    write(repo_root / "config" / "controller-local-secrets.json", json.dumps({"secrets": {}}, indent=2) + "\n")
    write(repo_root / "config" / "disaster-recovery-targets.json", json.dumps({"platform_target": {}}, indent=2) + "\n")
    write(repo_root / "docs" / "adr" / "0181.md", "# ADR\n")
    write(repo_root / "docs" / "runbooks" / "disaster-recovery.md", "# DR\n")
    write(repo_root / "docs" / "workstreams" / "adr-0181.md", "# WS\n")
    write(repo_root / "inventory" / "hosts.yml", "all: {}\n")
    write(repo_root / "inventory" / "group_vars" / "all.yml", "control: true\n")
    write(repo_root / "inventory" / "host_vars" / "proxmox_florin.yml", "host: true\n")
    write(repo_root / "versions" / "stack.yaml", "repo_version: 0.176.0\n")
    write(repo_root / "receipts" / "live-applies" / "example.json", json.dumps({"receipt_id": "example"}, indent=2) + "\n")

    assert git(repo_root, "add", ".").returncode == 0
    assert git(repo_root, "commit", "-m", "seed witness test repo").returncode == 0
    assert git(repo_root, "push", "-u", "origin", "main").returncode == 0
    return repo_root, remote_root


def test_sync_builds_verified_generation_and_receipt(tmp_path: Path) -> None:
    repo_root, _ = build_repo(tmp_path)
    archive_root = tmp_path / "archive"
    staging_root = tmp_path / "staging"
    receipt_dir = tmp_path / "receipts"

    generation_dir, receipt_path, receipt = witness.sync_control_metadata_witness(
        repo_root,
        archive_root=archive_root,
        staging_root=staging_root,
        receipt_dir=receipt_dir,
    )

    assert generation_dir.exists()
    assert receipt_path.exists()
    assert receipt["targets"]["git_remote"]["status"] == "pass"
    latest_target = (archive_root / "latest").resolve()
    assert latest_target == generation_dir
    manifest = json.loads((generation_dir / "witness-manifest.json").read_text(encoding="utf-8"))
    assert manifest["head_commit"] == git(repo_root, "rev-parse", "HEAD").stdout.strip()
    assert (generation_dir / "repo.bundle").exists()
    assert (generation_dir / "repo-snapshot.tar").exists()
    witness.verify_generation(generation_dir)


def test_sync_preserves_previous_latest_when_archive_promotion_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root, _ = build_repo(tmp_path)
    archive_root = tmp_path / "archive"
    staging_root = tmp_path / "staging"
    receipt_dir = tmp_path / "receipts"

    first_generation, _, _ = witness.sync_control_metadata_witness(
        repo_root,
        archive_root=archive_root,
        staging_root=staging_root,
        receipt_dir=receipt_dir,
    )

    write(repo_root / "receipts" / "live-applies" / "second.json", json.dumps({"receipt_id": "second"}, indent=2) + "\n")
    assert git(repo_root, "add", "receipts/live-applies/second.json").returncode == 0
    assert git(repo_root, "commit", "-m", "second receipt").returncode == 0
    assert git(repo_root, "push", "origin", "main").returncode == 0

    original_verify_generation = witness.verify_generation

    def explode_once(generation_dir: Path) -> dict[str, object]:
        if generation_dir.parent.name == ".staging":
            raise RuntimeError("simulated archive promotion failure")
        return original_verify_generation(generation_dir)

    monkeypatch.setattr(witness, "verify_generation", explode_once)

    with pytest.raises(RuntimeError, match="simulated archive promotion failure"):
        witness.sync_control_metadata_witness(
            repo_root,
            archive_root=archive_root,
            staging_root=staging_root,
            receipt_dir=receipt_dir,
        )

    latest_target = (archive_root / "latest").resolve()
    assert latest_target == first_generation
    assert not any((archive_root / ".staging").iterdir())


def test_sync_requires_remote_ref_to_match_current_head(tmp_path: Path) -> None:
    repo_root, _ = build_repo(tmp_path)
    write(repo_root / "README.md", "# Changed Locally\n")
    assert git(repo_root, "add", "README.md").returncode == 0
    assert git(repo_root, "commit", "-m", "local only").returncode == 0

    with pytest.raises(RuntimeError, match="expected current HEAD"):
        witness.sync_control_metadata_witness(
            repo_root,
            archive_root=tmp_path / "archive",
            staging_root=tmp_path / "staging",
            receipt_dir=tmp_path / "receipts",
        )


def test_resolve_remote_ref_prefers_current_branch_when_upstream_points_at_main(tmp_path: Path) -> None:
    repo_root, _ = build_repo(tmp_path)
    assert git(repo_root, "checkout", "-b", "feature/witness", "--track", "origin/main").returncode == 0

    resolved = witness.resolve_remote_ref(repo_root, "origin", None)

    assert resolved == "refs/heads/feature/witness"


def test_sync_uses_git_toplevel_when_invoked_from_scoped_shard_copy(tmp_path: Path) -> None:
    repo_root, _ = build_repo(tmp_path)
    shard_root = repo_root / ".ansible" / "shards"
    shard_root.mkdir(parents=True)

    for child in repo_root.iterdir():
        if child.name in {".git", ".ansible"}:
            continue
        target = shard_root / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)

    archive_root = tmp_path / "archive"
    staging_root = shard_root / ".local" / "control-metadata-witness" / "staging"
    receipt_dir = tmp_path / "receipts"

    generation_dir, receipt_path, receipt = witness.sync_control_metadata_witness(
        shard_root,
        archive_root=archive_root,
        staging_root=staging_root,
        receipt_dir=receipt_dir,
    )

    assert generation_dir.exists()
    assert receipt_path.exists()
    assert receipt["head_commit"] == git(repo_root, "rev-parse", "HEAD").stdout.strip()
    witness.verify_generation(generation_dir)
