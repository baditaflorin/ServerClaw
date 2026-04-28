"""Unit tests for scripts/heal_workstream_renames.py — ADR 0450 phase 5.2.

Exercises the rename-detection + YAML-rewrite path against synthetic
workstream trees. Real git rename detection runs in `--since` mode and
is exercised by a single integration test that mocks subprocess.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "heal_workstream_renames.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("heal_workstream_renames", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["heal_workstream_renames"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hwr():
    return _load_module()


# ---------------------------------------------------------------------------
# parse_renames_from_git_diff
# ---------------------------------------------------------------------------


def test_parse_renames_from_git_diff_tab_separated(hwr):
    out = hwr.parse_renames_from_git_diff("R100\told/path.yml\tnew/path.yml\n")
    assert out == [hwr.Rename(old="old/path.yml", new="new/path.yml")]


def test_parse_renames_handles_multiple_pairs(hwr):
    text = dedent(
        """
        R095\tinventory/group_vars/platform_services.yml\tinventory/group_vars/all/platform_services.yml
        R100\troles/foo/x.yml\troles/bar/x.yml
        """
    ).strip()
    out = hwr.parse_renames_from_git_diff(text)
    assert len(out) == 2
    assert out[0].old.endswith("platform_services.yml")
    assert out[1].new.startswith("roles/bar/")


def test_parse_renames_skips_non_rename_lines(hwr):
    text = "M\tedited.yml\nA\tadded.yml\nR100\tA\tB\n"
    out = hwr.parse_renames_from_git_diff(text)
    assert len(out) == 1
    assert out[0].old == "A"


def test_parse_renames_skips_old_equals_new(hwr):
    text = "R100\tsame.yml\tsame.yml\n"
    assert hwr.parse_renames_from_git_diff(text) == []


# ---------------------------------------------------------------------------
# parse_pair_args
# ---------------------------------------------------------------------------


def test_parse_pair_args_happy_path(hwr):
    out = hwr.parse_pair_args(["a:b", "c/d/e:c/d/e2"])
    assert out == [hwr.Rename("a", "b"), hwr.Rename("c/d/e", "c/d/e2")]


def test_parse_pair_args_rejects_missing_colon(hwr):
    with pytest.raises(ValueError, match="OLD:NEW"):
        hwr.parse_pair_args(["no-colon"])


def test_parse_pair_args_rejects_empty_side(hwr):
    with pytest.raises(ValueError, match="empty side"):
        hwr.parse_pair_args(["foo:"])


# ---------------------------------------------------------------------------
# rewrite_one_file
# ---------------------------------------------------------------------------


def _make_ws_yaml(tmp_path: Path, body: str) -> Path:
    """Create a workstream YAML at workstreams/active/ws-x.yaml under tmp_path."""
    p = tmp_path / "workstreams" / "active" / "ws-x.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def test_rewrite_one_file_replaces_exact_match(hwr, tmp_path):
    p = _make_ws_yaml(
        tmp_path,
        dedent(
            """\
            id: ws-x
            shared_surfaces:
              - inventory/group_vars/platform_services.yml
              - other/file.yml
            summary: |
              Mentions inventory/group_vars/platform_services.yml in prose.
              That mention should NOT be rewritten — only the list entry.
            """
        ),
    )
    rename = hwr.Rename(
        old="inventory/group_vars/platform_services.yml",
        new="inventory/group_vars/all/platform_services.yml",
    )
    results = hwr.rewrite_one_file(p, [rename], repo_root=tmp_path, apply=True)
    assert len(results) == 1
    text = p.read_text()
    # List entry was rewritten.
    assert "  - inventory/group_vars/all/platform_services.yml" in text
    # Prose mention was NOT rewritten.
    assert "Mentions inventory/group_vars/platform_services.yml in prose" in text


def test_rewrite_one_file_dry_run_does_not_mutate(hwr, tmp_path):
    p = _make_ws_yaml(
        tmp_path,
        dedent(
            """\
            shared_surfaces:
              - old/path.yml
            """
        ),
    )
    original = p.read_text()
    results = hwr.rewrite_one_file(
        p,
        [hwr.Rename(old="old/path.yml", new="new/path.yml")],
        repo_root=tmp_path,
        apply=False,
    )
    assert len(results) == 1  # detected
    assert p.read_text() == original  # but not written


def test_rewrite_one_file_preserves_inline_comment(hwr, tmp_path):
    p = _make_ws_yaml(
        tmp_path,
        dedent(
            """\
            shared_surfaces:
              - old/path.yml  # important note
            """
        ),
    )
    hwr.rewrite_one_file(
        p,
        [hwr.Rename(old="old/path.yml", new="new/path.yml")],
        repo_root=tmp_path,
        apply=True,
    )
    text = p.read_text()
    assert "- new/path.yml" in text
    assert "important note" in text


def test_rewrite_one_file_skips_outside_shared_surfaces(hwr, tmp_path):
    """A path matching `<old>` outside the shared_surfaces block must
    not be rewritten — e.g. in `notes:`, `summary:`, or another list."""
    p = _make_ws_yaml(
        tmp_path,
        dedent(
            """\
            shared_surfaces:
              - other/file.yml
            depends_on:
              - old/path.yml
            """
        ),
    )
    hwr.rewrite_one_file(
        p,
        [hwr.Rename(old="old/path.yml", new="new/path.yml")],
        repo_root=tmp_path,
        apply=True,
    )
    text = p.read_text()
    # Outside shared_surfaces, the path stays.
    assert "  - old/path.yml" in text


def test_rewrite_one_file_handles_no_match(hwr, tmp_path):
    p = _make_ws_yaml(
        tmp_path,
        dedent(
            """\
            shared_surfaces:
              - some/path.yml
            """
        ),
    )
    results = hwr.rewrite_one_file(
        p,
        [hwr.Rename(old="ghost.yml", new="phantom.yml")],
        repo_root=tmp_path,
        apply=True,
    )
    assert results == []


def test_rewrite_one_file_handles_multiple_renames(hwr, tmp_path):
    p = _make_ws_yaml(
        tmp_path,
        dedent(
            """\
            shared_surfaces:
              - a/old1.yml
              - b/old2.yml
              - c/unchanged.yml
            """
        ),
    )
    renames = [
        hwr.Rename(old="a/old1.yml", new="a/new1.yml"),
        hwr.Rename(old="b/old2.yml", new="b/new2.yml"),
    ]
    results = hwr.rewrite_one_file(p, renames, repo_root=tmp_path, apply=True)
    assert len(results) == 2
    text = p.read_text()
    assert "a/new1.yml" in text
    assert "b/new2.yml" in text
    assert "c/unchanged.yml" in text


# ---------------------------------------------------------------------------
# rewrite_all
# ---------------------------------------------------------------------------


def test_rewrite_all_walks_active_and_archive(hwr, tmp_path):
    """The archive tree is included so legacy workstreams stay clean."""
    active = tmp_path / "workstreams" / "active"
    archive = tmp_path / "workstreams" / "archive" / "2026"
    active.mkdir(parents=True)
    archive.mkdir(parents=True)
    (active / "ws-active.yaml").write_text(
        dedent(
            """\
            shared_surfaces:
              - old/path.yml
            """
        )
    )
    (archive / "ws-old.yaml").write_text(
        dedent(
            """\
            shared_surfaces:
              - old/path.yml
            """
        )
    )
    rename = hwr.Rename(old="old/path.yml", new="new/path.yml")
    results = hwr.rewrite_all([rename], repo_root=tmp_path, apply=True)
    assert len(results) == 2  # both files rewritten
    paths = {r.workstream_yaml for r in results}
    assert any("active/ws-active.yaml" in p for p in paths)
    assert any("archive/2026/ws-old.yaml" in p for p in paths)


def test_rewrite_all_skips_underscore_and_dotfiles(hwr, tmp_path):
    active = tmp_path / "workstreams" / "active"
    active.mkdir(parents=True)
    (active / "_TEMPLATE.yaml").write_text(
        dedent(
            """\
            shared_surfaces:
              - old/path.yml
            """
        )
    )
    (active / ".hidden.yaml").write_text(
        dedent(
            """\
            shared_surfaces:
              - old/path.yml
            """
        )
    )
    results = hwr.rewrite_all(
        [hwr.Rename(old="old/path.yml", new="new/path.yml")],
        repo_root=tmp_path,
        apply=True,
    )
    assert results == []


def test_rewrite_all_handles_empty_renames(hwr, tmp_path):
    assert hwr.rewrite_all([], repo_root=tmp_path, apply=False) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_no_args_returns_two(hwr, capsys):
    rc = hwr.main([])
    assert rc == 2


def test_cli_pair_dry_run_does_not_mutate(hwr, tmp_path, capsys):
    active = tmp_path / "workstreams" / "active"
    active.mkdir(parents=True)
    yaml_path = active / "ws-x.yaml"
    yaml_path.write_text(
        dedent(
            """\
            shared_surfaces:
              - old/path.yml
            """
        )
    )
    original = yaml_path.read_text()
    rc = hwr.main(["--pair", "old/path.yml:new/path.yml", "--root", str(tmp_path)])
    assert rc == 0
    assert yaml_path.read_text() == original
    out = capsys.readouterr().out
    assert "would rewrite 1" in out
    assert "Re-run with --apply" in out


def test_cli_pair_apply_mutates(hwr, tmp_path, capsys):
    active = tmp_path / "workstreams" / "active"
    active.mkdir(parents=True)
    yaml_path = active / "ws-x.yaml"
    yaml_path.write_text(
        dedent(
            """\
            shared_surfaces:
              - old/path.yml
            """
        )
    )
    rc = hwr.main(
        [
            "--pair",
            "old/path.yml:new/path.yml",
            "--apply",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert "new/path.yml" in yaml_path.read_text()


def test_cli_no_renames_detected_returns_zero(hwr, tmp_path, monkeypatch, capsys):
    """`--since` with a stub git that returns nothing → exit 0, no work."""
    monkeypatch.setattr(hwr, "detect_renames_via_git", lambda since, repo_root: [])
    rc = hwr.main(["--since", "ORIG_HEAD", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no renames detected" in out


def test_cli_invalid_pair_returns_two(hwr, tmp_path, capsys):
    rc = hwr.main(["--pair", "no-colon", "--root", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "OLD:NEW" in err
