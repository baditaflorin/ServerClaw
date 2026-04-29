"""Unit tests for scripts/generate_pr_body.py — ADR 0473 phase 11.3."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_pr_body.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_pr_body", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["generate_pr_body"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gpb():
    return _load_module()


def test_read_version_missing_returns_unknown(gpb, tmp_path):
    assert gpb.read_version(tmp_path / "nope") == "(unknown)"


def test_read_version_strips_whitespace(gpb, tmp_path):
    p = tmp_path / "VERSION"
    p.write_text("0.1.2\n")
    assert gpb.read_version(p) == "0.1.2"


def test_extract_unreleased_returns_bullets(gpb, tmp_path):
    p = tmp_path / "changelog.md"
    p.write_text("# Changelog\n\n## Unreleased\n\n- entry one\n- entry two\n  continuation\n\n## Latest Release\n")
    bullets = gpb.extract_unreleased(p)
    assert "entry one" in bullets
    assert any("continuation" in b for b in bullets)


def test_extract_unreleased_handles_missing_section(gpb, tmp_path):
    p = tmp_path / "changelog.md"
    p.write_text("# Changelog\n")
    assert gpb.extract_unreleased(p) == []


def test_extract_unreleased_handles_missing_file(gpb, tmp_path):
    assert gpb.extract_unreleased(tmp_path / "nope") == []


def test_find_adr_refs_extracts_unique(gpb):
    bullets = ["ADR 0472 fixes ADR 0470", "ADR 0473 new"]
    refs = gpb.find_adr_refs(bullets)
    assert refs == ["ADR 0472", "ADR 0470", "ADR 0473"]


def test_find_adr_refs_no_match(gpb):
    assert gpb.find_adr_refs(["just text"]) == []


def test_render_full(gpb):
    body = gpb.render(
        version="1.2.3",
        bullets=["bullet a", "bullet b"],
        artifacts={"VERSION": True, "missing": False},
        probes=["receipts/health-probes/x.yaml"],
        adrs=["ADR 0472"],
    )
    assert "## Summary" in body
    assert "- bullet a" in body
    assert "- [x] VERSION" in body
    assert "- [ ] missing" in body
    assert "## Test plan" in body
    assert "receipts/health-probes/x.yaml" in body
    assert "## ADR refs" in body
    assert "- ADR 0472" in body
    assert "version 1.2.3" in body


def test_render_no_bullets_emits_placeholder(gpb):
    body = gpb.render(version="1", bullets=[], artifacts={}, probes=[], adrs=[])
    assert "(no Unreleased entries found)" in body


def test_render_no_probes_emits_placeholder(gpb):
    body = gpb.render(version="1", bullets=["x"], artifacts={}, probes=[], adrs=[])
    assert "(no health-probe receipts found" in body


def test_render_omits_adr_section_when_empty(gpb):
    body = gpb.render(version="1", bullets=["x"], artifacts={}, probes=[], adrs=[])
    assert "## ADR refs" not in body


def test_main_stdout(gpb, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(gpb, "VERSION_PATH", tmp_path / "VERSION")
    monkeypatch.setattr(gpb, "CHANGELOG_PATH", tmp_path / "changelog.md")
    monkeypatch.setattr(gpb, "RELEASE_NOTES_DIR", tmp_path / "release-notes")
    monkeypatch.setattr(gpb, "HEALTH_PROBES_DIR", tmp_path / "probes")
    (tmp_path / "VERSION").write_text("0.1.0\n")
    (tmp_path / "changelog.md").write_text("## Unreleased\n\n- thing\n\n## Latest Release\n")
    rc = gpb.main([])
    assert rc == 0
    assert "thing" in capsys.readouterr().out


def test_main_write(gpb, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(gpb, "VERSION_PATH", tmp_path / "VERSION")
    monkeypatch.setattr(gpb, "CHANGELOG_PATH", tmp_path / "changelog.md")
    monkeypatch.setattr(gpb, "RELEASE_NOTES_DIR", tmp_path / "release-notes")
    monkeypatch.setattr(gpb, "HEALTH_PROBES_DIR", tmp_path / "probes")
    (tmp_path / "VERSION").write_text("0.1.0\n")
    (tmp_path / "changelog.md").write_text("## Unreleased\n\n- thing\n\n## Latest Release\n")
    out = tmp_path / "draft.md"
    rc = gpb.main(["--write", "--output", str(out)])
    assert rc == 0
    assert out.is_file()
    assert "thing" in out.read_text()


def test_recent_health_probes_handles_missing_dir(gpb, tmp_path):
    assert gpb.recent_health_probes(probes_dir=tmp_path / "nope") == []
