from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "repository_snapshot.py"


def load_module():
    spec = importlib.util.spec_from_file_location("repository_snapshot", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "codex@example.com"], cwd=path, check=True, capture_output=True, text=True
    )


def commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True, text=True)


def test_build_snapshot_writes_archive_and_manifest(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / ".rsync-exclude").write_text(".local/\n*.vault\n", encoding="utf-8")
    (repo / "README.md").write_text("snapshot test\n", encoding="utf-8")
    (repo / "config").mkdir()
    (repo / "config" / "app.json").write_text('{"ok": true}\n', encoding="utf-8")
    (repo / ".local").mkdir()
    (repo / ".local" / "secret.txt").write_text("hidden\n", encoding="utf-8")
    (repo / "secrets.vault").write_text("hidden\n", encoding="utf-8")
    commit_all(repo, "initial")

    output_dir = tmp_path / "out"
    payload = module.build_snapshot(repo, exclude_file=repo / ".rsync-exclude", output_dir=output_dir)

    manifest_path = Path(payload["LV3_SNAPSHOT_MANIFEST"])
    archive_path = Path(payload["LV3_SNAPSHOT_ARCHIVE"])
    assert manifest_path.exists()
    assert archive_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == payload["LV3_SNAPSHOT_ID"]
    assert manifest["branch"] == "main"
    assert manifest["source_commit"] != "unknown"
    assert all(entry["path"] != ".local/secret.txt" for entry in manifest["entries"])
    assert all(entry["path"] != "secrets.vault" for entry in manifest["entries"])

    with tarfile.open(archive_path, "r:gz") as archive:
        names = sorted(member.name for member in archive.getmembers())
    assert "metadata/manifest.json" in names
    assert "repo/README.md" in names
    assert "repo/config/app.json" in names
    assert "repo/.local/secret.txt" not in names
    assert "repo/secrets.vault" not in names


def test_snapshot_id_is_stable_for_same_repo_content(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "README.md").write_text("same\n", encoding="utf-8")
    commit_all(repo, "initial")

    first = module.build_snapshot(repo, exclude_file=None, output_dir=tmp_path / "first")
    second = module.build_snapshot(repo, exclude_file=None, output_dir=tmp_path / "second")

    assert first["LV3_SNAPSHOT_ID"] == second["LV3_SNAPSHOT_ID"]
    assert first["LV3_SNAPSHOT_ARCHIVE"] != second["LV3_SNAPSHOT_ARCHIVE"]


def test_build_snapshot_honors_explicit_branch_override(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "README.md").write_text("override\n", encoding="utf-8")
    commit_all(repo, "initial")

    monkeypatch.setenv("LV3_SNAPSHOT_BRANCH", "main")
    payload = module.build_snapshot(repo, exclude_file=None, output_dir=tmp_path / "out")

    manifest = json.loads(Path(payload["LV3_SNAPSHOT_MANIFEST"]).read_text(encoding="utf-8"))
    assert payload["LV3_SNAPSHOT_BRANCH"] == "main"
    assert manifest["branch"] == "main"
