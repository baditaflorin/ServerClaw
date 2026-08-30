from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import materialize_bootstrap_key_alias as bootstrap_alias


def test_ensure_bootstrap_key_aliases_materializes_relative_symlinks(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    ssh_dir = repo_root / ".local" / "ssh"
    ssh_dir.mkdir(parents=True)
    legacy_private = ssh_dir / "hetzner_llm_agents_ed25519"
    legacy_public = ssh_dir / "hetzner_llm_agents_ed25519.pub"
    legacy_private.write_text("PRIVATE\n", encoding="utf-8")
    legacy_public.write_text("PUBLIC\n", encoding="utf-8")

    results = bootstrap_alias.ensure_bootstrap_key_aliases(repo_root)

    alias_private = ssh_dir / "bootstrap.id_ed25519"
    alias_public = ssh_dir / "bootstrap.id_ed25519.pub"
    assert [item.status for item in results] == ["materialized", "materialized"]
    assert alias_private.is_symlink()
    assert alias_private.resolve() == legacy_private
    assert alias_private.read_text(encoding="utf-8") == "PRIVATE\n"
    assert alias_public.is_symlink()
    assert alias_public.resolve() == legacy_public
    assert alias_public.read_text(encoding="utf-8") == "PUBLIC\n"


def test_ensure_bootstrap_key_aliases_reports_present_aliases_without_rewriting(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    ssh_dir = repo_root / ".local" / "ssh"
    ssh_dir.mkdir(parents=True)
    alias_private = ssh_dir / "bootstrap.id_ed25519"
    alias_public = ssh_dir / "bootstrap.id_ed25519.pub"
    alias_private.write_text("PRIVATE\n", encoding="utf-8")
    alias_public.write_text("PUBLIC\n", encoding="utf-8")

    results = bootstrap_alias.ensure_bootstrap_key_aliases(repo_root)

    assert [item.status for item in results] == ["present", "present"]


def test_ensure_bootstrap_key_aliases_accepts_a_same_path_creation_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    ssh_dir = repo_root / ".local" / "ssh"
    ssh_dir.mkdir(parents=True)
    legacy_private = ssh_dir / "hetzner_llm_agents_ed25519"
    legacy_public = ssh_dir / "hetzner_llm_agents_ed25519.pub"
    legacy_private.write_text("PRIVATE\n", encoding="utf-8")
    legacy_public.write_text("PUBLIC\n", encoding="utf-8")

    real_create = bootstrap_alias._create_relative_symlink

    def create_then_report_race(alias_path: Path, target_path: Path) -> None:
        real_create(alias_path, target_path)
        raise FileExistsError(alias_path)

    monkeypatch.setattr(bootstrap_alias, "_create_relative_symlink", create_then_report_race)

    results = bootstrap_alias.ensure_bootstrap_key_aliases(repo_root)

    assert [item.status for item in results] == ["present", "present"]
    assert (ssh_dir / "bootstrap.id_ed25519").resolve() == legacy_private
    assert (ssh_dir / "bootstrap.id_ed25519.pub").resolve() == legacy_public
