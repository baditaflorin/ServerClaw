"""Unit tests for scripts/generate_context_packs.py — ADR 0473 phase 11.4."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_context_packs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_context_packs", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["generate_context_packs"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gcp():
    return _load_module()


def _setup_workstreams(tmp_path: Path) -> tuple[Path, Path, Path]:
    ws_dir = tmp_path / "workstreams" / "active"
    ws_dir.mkdir(parents=True)
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    changelog = tmp_path / "changelog.md"
    return ws_dir, adr_dir, changelog


def test_discover_workstreams_handles_missing_dir(gcp, tmp_path):
    assert gcp.discover_workstreams(tmp_path / "nope") == []


def test_discover_workstreams_picks_up_yaml_files(gcp, tmp_path):
    d = tmp_path / "ws"
    d.mkdir()
    (d / "ws-1.yaml").write_text("id: ws-1")
    (d / "ws-2.yaml").write_text("id: ws-2")
    (d / "not-a-ws.txt").write_text("ignore")
    found = [p.name for p in gcp.discover_workstreams(d)]
    assert found == ["ws-1.yaml", "ws-2.yaml"]


def test_load_workstream_rejects_non_mapping(gcp, tmp_path):
    p = tmp_path / "ws.yaml"
    p.write_text("- not-a-mapping")
    with pytest.raises(ValueError):
        gcp.load_workstream(p)


def test_find_adr_path_resolves_zero_pad(gcp, tmp_path):
    (tmp_path / "0473-test-adr.md").write_text("hi")
    assert gcp.find_adr_path("0473", tmp_path) == tmp_path / "0473-test-adr.md"


def test_find_adr_path_handles_int(gcp, tmp_path):
    (tmp_path / "0473-test-adr.md").write_text("hi")
    assert gcp.find_adr_path(473, tmp_path) == tmp_path / "0473-test-adr.md"


def test_find_adr_path_no_match(gcp, tmp_path):
    assert gcp.find_adr_path("9999", tmp_path) is None


def test_find_adr_path_empty(gcp, tmp_path):
    assert gcp.find_adr_path(None, tmp_path) is None


def test_changelog_bullets_mentioning_finds_ws_id(gcp, tmp_path):
    p = tmp_path / "changelog.md"
    p.write_text("## Unreleased\n\n- ws-0473 + ADR 0473: thing\n- unrelated entry\n")
    bullets = gcp.changelog_bullets_mentioning("ws-0473", p)
    assert len(bullets) == 1
    assert "ws-0473" in bullets[0]


def test_changelog_bullets_handles_missing_file(gcp, tmp_path):
    assert gcp.changelog_bullets_mentioning("ws-x", tmp_path / "nope") == []


def test_render_pack_includes_adr_when_present(gcp, tmp_path):
    ws_path = tmp_path / "ws-0474.yaml"
    ws_path.write_text("id: ws-0474\nadr: '0473'\n")
    adr_path = tmp_path / "0473-foo.md"
    adr_path.write_text("# ADR 0473\n\nbody")
    body = gcp.render_pack(
        workstream_path=ws_path,
        ws_payload={"id": "ws-0474", "adr": "0473", "title": "Foo", "status": "in_progress"},
        adr_path=adr_path,
        bullets=["mention ws-0474"],
    )
    assert "Context pack — ws-0474" in body
    assert "Title:** Foo" in body
    assert "## Workstream registry entry" in body
    assert "## ADR" in body
    assert "ADR 0473" in body
    assert "## Recent changelog mentions" in body
    assert "mention ws-0474" in body


def test_render_pack_omits_adr_when_missing(gcp, tmp_path):
    ws_path = tmp_path / "ws-1.yaml"
    body = gcp.render_pack(
        workstream_path=ws_path,
        ws_payload={"id": "ws-1", "title": "x"},
        adr_path=None,
        bullets=[],
    )
    assert "## ADR" not in body
    assert "## Recent changelog mentions" not in body


def test_render_index(gcp):
    out = gcp.render_index([("ws-1", "Title A"), ("ws-2", "Title B")])
    assert "2 active workstreams" in out
    assert "[ws-1](ws-1.md) — Title A" in out


def test_write_or_check_writes_files(gcp, tmp_path):
    ws_dir, adr_dir, changelog = _setup_workstreams(tmp_path)
    (ws_dir / "ws-0001-test.yaml").write_text(yaml.safe_dump({"id": "ws-0001-test", "adr": "0001"}))
    (adr_dir / "0001-test.md").write_text("# ADR 0001\n")
    changelog.write_text("- ws-0001-test mentioned\n")
    output = tmp_path / "out"
    rc = gcp.write_or_check(
        output_dir=output,
        workstreams_dir=ws_dir,
        adr_dir=adr_dir,
        changelog_path=changelog,
        check=False,
    )
    assert rc == 0
    assert (output / "ws-0001-test.md").is_file()
    assert (output / "index.md").is_file()


def test_write_or_check_clean_check_passes(gcp, tmp_path):
    ws_dir, adr_dir, changelog = _setup_workstreams(tmp_path)
    (ws_dir / "ws-1.yaml").write_text("id: ws-1")
    changelog.write_text("")
    output = tmp_path / "out"
    gcp.write_or_check(
        output_dir=output,
        workstreams_dir=ws_dir,
        adr_dir=adr_dir,
        changelog_path=changelog,
        check=False,
    )
    rc = gcp.write_or_check(
        output_dir=output,
        workstreams_dir=ws_dir,
        adr_dir=adr_dir,
        changelog_path=changelog,
        check=True,
    )
    assert rc == 0


def test_write_or_check_drift_check_fails(gcp, tmp_path, capsys):
    ws_dir, adr_dir, changelog = _setup_workstreams(tmp_path)
    (ws_dir / "ws-1.yaml").write_text("id: ws-1")
    changelog.write_text("")
    output = tmp_path / "out"
    output.mkdir()
    (output / "ws-1.md").write_text("stale\n")
    rc = gcp.write_or_check(
        output_dir=output,
        workstreams_dir=ws_dir,
        adr_dir=adr_dir,
        changelog_path=changelog,
        check=True,
    )
    assert rc == 1


def test_main_returns_0_on_write(gcp, tmp_path):
    ws_dir, adr_dir, changelog = _setup_workstreams(tmp_path)
    (ws_dir / "ws-1.yaml").write_text("id: ws-1")
    changelog.write_text("")
    output = tmp_path / "out"
    rc = gcp.main(
        [
            "--workstreams-dir",
            str(ws_dir),
            "--adr-dir",
            str(adr_dir),
            "--changelog-path",
            str(changelog),
            "--output-dir",
            str(output),
        ]
    )
    assert rc == 0


def test_main_returns_1_on_drift(gcp, tmp_path):
    ws_dir, adr_dir, changelog = _setup_workstreams(tmp_path)
    (ws_dir / "ws-1.yaml").write_text("id: ws-1")
    changelog.write_text("")
    output = tmp_path / "out"
    output.mkdir()
    (output / "ws-1.md").write_text("stale\n")
    rc = gcp.main(
        [
            "--workstreams-dir",
            str(ws_dir),
            "--adr-dir",
            str(adr_dir),
            "--changelog-path",
            str(changelog),
            "--output-dir",
            str(output),
            "--check",
        ]
    )
    assert rc == 1
