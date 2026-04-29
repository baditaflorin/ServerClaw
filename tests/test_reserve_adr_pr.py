"""Unit tests for scripts/reserve_adr_pr.py — ADR 0472 phase 10.1.

The full happy path involves git checkout + push + gh-cli; we don't
exercise that end-to-end (it would mutate real branches). Tests
cover the deterministic helpers — entry construction, slug
synthesis, precheck — plus a fully-mocked CLI run that pins the
sequence of helper calls.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "reserve_adr_pr.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("reserve_adr_pr", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["reserve_adr_pr"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rap():
    return _load_module()


# ---------------------------------------------------------------------------
# build_reservation_entry
# ---------------------------------------------------------------------------


def test_build_reservation_entry_shape(rap):
    entry = rap.build_reservation_entry(
        number=467,
        reason="phase 10 reservation hardening",
        workstream="ws-0467",
        branch="reservation/0467",
        owner="claude",
        today=dt.date(2026, 4, 29),
    )
    # Schema must match scripts/adr_discovery.py::AdrReservation
    # (which requires `id`, not `reservation_id`).
    assert entry["id"].startswith("res-0467-")
    assert entry["start"] == 467
    assert entry["end"] == 467
    assert entry["status"] == "active"
    assert entry["reserved_on"] == "2026-04-29"
    assert entry["expires_on"] == "2026-05-29"
    assert entry["workstream"] == "ws-0467"


def test_build_reservation_entry_slugifies_long_reason(rap):
    """Mirrors reserve_adr.py — reason → kebab-case slug, capped at
    40 chars so the id field stays grep-friendly."""
    entry = rap.build_reservation_entry(
        number=500,
        reason="A very long reason !@#$ with special chars that goes way past 40 characters",
        workstream="x",
        branch="b",
        owner="o",
        today=dt.date(2026, 4, 29),
    )
    suffix = entry["id"].split("-", 2)[-1]
    assert len(suffix) <= 40
    assert all(c.isalnum() or c == "-" for c in suffix)


def test_build_reservation_entry_unassigned_workstream(rap):
    """Empty workstream falls back to `unassigned` so the entry is
    still well-formed for the loader's strict checks."""
    entry = rap.build_reservation_entry(
        number=467,
        reason="x",
        workstream="",
        branch="b",
        owner="o",
        today=dt.date(2026, 4, 29),
    )
    assert entry["workstream"] == "unassigned"


# ---------------------------------------------------------------------------
# _slug
# ---------------------------------------------------------------------------


def test_slug_normalises_punctuation(rap):
    assert rap._slug("Phase 10 — fix ADR collision class!") == "phase-10-fix-adr-collision-class"


def test_slug_falls_back_to_unspecified(rap):
    assert rap._slug("!!!") == "unspecified"
    assert rap._slug("") == "unspecified"


# ---------------------------------------------------------------------------
# precheck — refusal cases
# ---------------------------------------------------------------------------


def test_precheck_refuses_when_gh_missing(rap, tmp_path, monkeypatch):
    def fake_has(name):
        return name != "gh"

    monkeypatch.setattr(rap, "_has_command", fake_has)
    ok, reason = rap.precheck(tmp_path)
    assert ok is False
    assert "gh" in reason


def test_precheck_refuses_when_git_missing(rap, tmp_path, monkeypatch):
    def fake_has(name):
        return name != "git"

    monkeypatch.setattr(rap, "_has_command", fake_has)
    ok, reason = rap.precheck(tmp_path)
    assert ok is False
    assert "git" in reason


def test_precheck_refuses_dirty_tree(rap, tmp_path, monkeypatch):
    monkeypatch.setattr(rap, "_has_command", lambda name: True)
    monkeypatch.setattr(rap, "_git", lambda args, cwd=None, check=True: " M Makefile\n")
    ok, reason = rap.precheck(tmp_path)
    assert ok is False
    assert "uncommitted" in reason


def test_precheck_passes_on_clean_tree(rap, tmp_path, monkeypatch):
    monkeypatch.setattr(rap, "_has_command", lambda name: True)
    monkeypatch.setattr(rap, "_git", lambda args, cwd=None, check=True: "")
    ok, reason = rap.precheck(tmp_path)
    assert ok is True
    assert reason == ""


# ---------------------------------------------------------------------------
# CLI happy path (fully mocked)
# ---------------------------------------------------------------------------


def test_cli_happy_path_returns_number_on_stdout(rap, tmp_path, monkeypatch, capsys):
    """End-to-end with every subprocess call mocked. Asserts the
    helper sequence and that the reserved number lands on stdout."""
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(rap, "precheck", lambda repo_root: (True, ""))
    monkeypatch.setattr(rap, "fetch_main", lambda repo_root, base: calls.append(("fetch_main", base)))
    monkeypatch.setattr(rap, "next_free_via_helper", lambda repo_root: 467)
    monkeypatch.setattr(rap, "_resolve_owner", lambda: "claude")
    monkeypatch.setattr(
        rap,
        "append_to_reservations_on_branch",
        lambda branch, repo_root, base, entry: calls.append(("append", branch, entry["id"])),
    )
    monkeypatch.setattr(
        rap,
        "push_and_open_pr",
        lambda branch, repo_root, base, entry: "https://github.com/x/y/pull/123",
    )
    monkeypatch.setattr(rap, "squash_merge", lambda branch, repo_root: True)
    monkeypatch.setattr(rap, "reset_to_origin", lambda repo_root, base: calls.append(("reset", base)))

    rc = rap.main(
        [
            "--reason",
            "phase 10 reservation hardening",
            "--workstream",
            "ws-0467",
            "--root",
            str(tmp_path),
        ],
        today=dt.date(2026, 4, 29),
    )
    assert rc == 0
    captured = capsys.readouterr()
    # Number lands on stdout for shell capture.
    assert captured.out.strip() == "0467"
    # Helper sequence: fetch → append → reset.
    names = [c[0] for c in calls]
    assert names == ["fetch_main", "append", "reset"]
    # Reservation entry id starts with res-0467-
    assert "res-0467-" in calls[1][2]


def test_cli_no_merge_skips_squash_step(rap, tmp_path, monkeypatch, capsys):
    """`--no-merge` opens the PR but doesn't call squash_merge. Used
    for branch-protected repos where the merge needs a human review."""
    merge_called = []

    monkeypatch.setattr(rap, "precheck", lambda repo_root: (True, ""))
    monkeypatch.setattr(rap, "fetch_main", lambda repo_root, base: None)
    monkeypatch.setattr(rap, "next_free_via_helper", lambda repo_root: 500)
    monkeypatch.setattr(rap, "_resolve_owner", lambda: "claude")
    monkeypatch.setattr(rap, "append_to_reservations_on_branch", lambda *a, **k: None)
    monkeypatch.setattr(rap, "push_and_open_pr", lambda *a, **k: "url")
    monkeypatch.setattr(rap, "squash_merge", lambda *a, **k: merge_called.append(1))
    monkeypatch.setattr(rap, "reset_to_origin", lambda *a, **k: None)

    rc = rap.main(
        [
            "--reason",
            "test",
            "--root",
            str(tmp_path),
            "--no-merge",
        ]
    )
    assert rc == 0
    assert merge_called == []  # squash_merge not invoked


def test_cli_precheck_failure_returns_one(rap, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rap, "precheck", lambda repo_root: (False, "gh missing"))
    rc = rap.main(["--reason", "x", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "gh missing" in err


def test_cli_next_free_helper_failure_returns_one(rap, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rap, "precheck", lambda repo_root: (True, ""))
    monkeypatch.setattr(rap, "fetch_main", lambda *a, **k: None)

    def boom(repo_root):
        raise RuntimeError("reserve_adr --next failed")

    monkeypatch.setattr(rap, "next_free_via_helper", boom)
    rc = rap.main(["--reason", "x", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "reserve_adr" in err


def test_cli_append_failure_returns_one(rap, tmp_path, monkeypatch, capsys):
    """If branch creation / append fails, the CLI returns 1 and
    surfaces the error — no half-state."""
    monkeypatch.setattr(rap, "precheck", lambda repo_root: (True, ""))
    monkeypatch.setattr(rap, "fetch_main", lambda *a, **k: None)
    monkeypatch.setattr(rap, "next_free_via_helper", lambda repo_root: 500)
    monkeypatch.setattr(rap, "_resolve_owner", lambda: "claude")

    def boom(*a, **k):
        raise RuntimeError("checkout failed")

    monkeypatch.setattr(rap, "append_to_reservations_on_branch", boom)
    rc = rap.main(["--reason", "x", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "checkout failed" in err
