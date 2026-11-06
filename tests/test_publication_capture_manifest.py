"""Captured configuration keeps exact checksums after public sanitization."""

from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
publisher = importlib.import_module("publish_to_serverclaw")
RELATIVE = Path(publisher.CAPTURED_FILE_MANIFESTS[0])


def capture(root: Path) -> tuple[Path, Path]:
    manifest = root / RELATIVE
    file = manifest.parent / "files" / "etc" / "buildkit" / "buildkitd.toml"
    file.parent.mkdir(parents=True)
    file.write_text('address = "https://internal.invalid:1234"\n')
    manifest.write_text(f"{hashlib.sha256(file.read_bytes()).hexdigest()}  etc/buildkit/buildkitd.toml\n")
    return manifest, file


def test_public_sanitization_refreshes_export_hashes_and_preserves_private_capture(tmp_path, monkeypatch):
    source = tmp_path / "source"
    original_manifest, original_file = capture(source)
    original = (original_manifest.read_bytes(), original_file.read_bytes())
    exported = tmp_path / "export"
    shutil.copytree(source, exported)
    exported_file = exported / original_file.relative_to(source)
    publisher.apply_string_replacements(
        exported,
        {"string_replacements": [{"pattern": r"internal\.invalid", "replacement": "example.invalid"}]},
    )
    assert "example.invalid" in exported_file.read_text()
    calls = []
    monkeypatch.setattr(publisher, "run", lambda command, **kwargs: calls.append((command, kwargs["cwd"])))

    publisher.regenerate_public_derived_artifacts(exported)

    manifest = exported / RELATIVE
    assert manifest.read_text() == f"{hashlib.sha256(exported_file.read_bytes()).hexdigest()}  etc/buildkit/buildkitd.toml\n"
    assert (original_manifest.read_bytes(), original_file.read_bytes()) == original
    assert calls == [(["make", "generate-platform-vars"], exported)] * 2
    before = manifest.read_bytes()
    publisher.regenerate_public_derived_artifacts(exported)
    assert manifest.read_bytes() == before


@pytest.mark.parametrize("change", ["extra", "missing", "escape", "duplicate", "symlink"])
def test_publication_does_not_bless_a_changed_capture_file_set(tmp_path, change):
    manifest, file = capture(tmp_path)
    before = manifest.read_bytes()
    if change == "extra":
        (file.parent / "extra.toml").write_text("unlisted")
    elif change == "missing":
        file.unlink()
    elif change == "escape":
        manifest.write_text(f"{'a' * 64}  ../outside\n")
    elif change == "duplicate":
        manifest.write_bytes(before * 2)
    else:
        file.unlink()
        file.symlink_to(tmp_path / "outside")
    before = manifest.read_bytes()
    with pytest.raises(ValueError):
        publisher.refresh_captured_file_manifests(tmp_path)
    assert manifest.read_bytes() == before


def test_partial_fixture_without_a_capture_manifest_is_unchanged(tmp_path):
    publisher.refresh_captured_file_manifests(tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("change", ["manifest_symlink", "files_symlink", "missing_root", "file_root"])
def test_publication_refuses_symlink_and_non_directory_capture_roots(tmp_path, change):
    manifest, file = capture(tmp_path / "export")
    before = manifest.read_bytes()
    files = manifest.parent / "files"
    external = tmp_path / "outside"
    if change == "manifest_symlink":
        manifest.rename(external)
        manifest.symlink_to(external)
    else:
        files.rename(external)
        if change == "files_symlink":
            files.symlink_to(external, target_is_directory=True)
        elif change == "file_root":
            files.write_text("not a directory")
    with pytest.raises(ValueError):
        publisher.refresh_captured_file_manifests(tmp_path / "export")
    assert manifest.read_bytes() == before


@pytest.mark.parametrize("ancestor", ["config", "config/0mcp", "config/0mcp/docker-build-lv3"])
def test_publication_refuses_symlinked_ancestors_without_changing_private_bytes(tmp_path, ancestor):
    private = tmp_path / "private"
    manifest, file = capture(private)
    manifest.write_bytes(manifest.read_bytes().replace(b"  ", b" ", 1))
    before = (manifest.read_bytes(), file.read_bytes())
    exported = tmp_path / "export"
    link = exported / ancestor
    link.parent.mkdir(parents=True)
    link.symlink_to(private / ancestor, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        publisher.refresh_captured_file_manifests(exported)

    assert (manifest.read_bytes(), file.read_bytes()) == before


def test_publication_refuses_a_symlinked_export_root(tmp_path):
    private = tmp_path / "private"
    manifest, file = capture(private)
    before = (manifest.read_bytes(), file.read_bytes())
    exported = tmp_path / "export"
    exported.symlink_to(private, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        publisher.refresh_captured_file_manifests(exported)
    assert (manifest.read_bytes(), file.read_bytes()) == before


def test_publication_refuses_a_capture_path_outside_the_export(tmp_path, monkeypatch):
    private = tmp_path / "private"
    manifest, file = capture(private)
    before = (manifest.read_bytes(), file.read_bytes())
    exported = tmp_path / "export"
    exported.mkdir()
    monkeypatch.setattr(publisher, "CAPTURED_FILE_MANIFESTS", ("../private/" + RELATIVE.as_posix(),))
    with pytest.raises(ValueError, match="escapes|outside"):
        publisher.refresh_captured_file_manifests(exported)
    assert (manifest.read_bytes(), file.read_bytes()) == before


def test_publication_refuses_a_manifest_hard_link_without_changing_private_bytes(tmp_path):
    manifest, private_file = capture(tmp_path / "private")
    manifest.write_bytes(manifest.read_bytes().replace(b"  ", b" ", 1))
    before = (manifest.read_bytes(), private_file.read_bytes())
    exported = tmp_path / "export"
    export_manifest, _ = capture(exported)
    export_manifest.unlink()
    os.link(manifest, export_manifest)
    with pytest.raises(ValueError, match="hard link"):
        publisher.refresh_captured_file_manifests(exported)
    assert (manifest.read_bytes(), private_file.read_bytes()) == before


def test_publication_refuses_to_refresh_the_source_checkout(tmp_path, monkeypatch):
    private = tmp_path / "private"
    manifest, file = capture(private)
    before = (manifest.read_bytes(), file.read_bytes())
    monkeypatch.setattr(publisher, "REPO_ROOT", private)
    with pytest.raises(ValueError, match="source checkout"):
        publisher.refresh_captured_file_manifests(private)
    assert (manifest.read_bytes(), file.read_bytes()) == before


def test_publication_refuses_a_case_alias_of_the_source_checkout(tmp_path, monkeypatch):
    private = tmp_path / "private"
    manifest, file = capture(private)
    alias = tmp_path / "PRIVATE"
    if not alias.exists() or not alias.samefile(private):
        pytest.skip("filesystem is case-sensitive")
    manifest.write_bytes(manifest.read_bytes().replace(b"  ", b" ", 1))
    before = (manifest.read_bytes(), file.read_bytes())
    monkeypatch.setattr(publisher, "REPO_ROOT", private)
    with pytest.raises(ValueError, match="source checkout"):
        publisher.refresh_captured_file_manifests(alias)
    assert (manifest.read_bytes(), file.read_bytes()) == before
