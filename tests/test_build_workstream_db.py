"""Unit tests for scripts/build_workstream_db.py — ADR 0473 phase 11.2."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_workstream_db.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_workstream_db", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["build_workstream_db"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bdb():
    return _load_module()


def _make_workstreams(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "workstreams.yaml"
    p.write_text(yaml.safe_dump({"workstreams": entries}))
    return p


def test_normalise_handles_missing_fields(bdb):
    out = bdb.normalise({"id": "ws-x"})
    assert out["id"] == "ws-x"
    assert out["adr"] is None
    assert out["ready_to_merge"] is None


def test_normalise_coerces_bool_to_int(bdb):
    out = bdb.normalise({"id": "ws-x", "ready_to_merge": True, "live_applied": False})
    assert out["ready_to_merge"] == 1
    assert out["live_applied"] == 0


def test_normalise_string_adr_preserved(bdb):
    out = bdb.normalise({"id": "ws-x", "adr": "0472"})
    assert out["adr"] == "0472"


def test_normalise_int_adr_stringified(bdb):
    out = bdb.normalise({"id": "ws-x", "adr": 472})
    assert out["adr"] == "472"


def test_load_workstreams_handles_missing_file(bdb, tmp_path):
    assert bdb.load_workstreams(tmp_path / "nope.yaml") == []


def test_load_workstreams_handles_non_list_field(bdb, tmp_path):
    p = tmp_path / "ws.yaml"
    p.write_text("workstreams: not-a-list")
    assert bdb.load_workstreams(p) == []


def test_load_workstreams_skips_entries_missing_id(bdb, tmp_path):
    p = _make_workstreams(tmp_path, [{"id": "ws-1"}, {"title": "no-id"}])
    rows = bdb.load_workstreams(p)
    assert len(rows) == 1
    assert rows[0]["id"] == "ws-1"


def test_workstreams_fingerprint_changes_with_content(bdb, tmp_path):
    p = tmp_path / "ws.yaml"
    p.write_text("workstreams: []")
    f1 = bdb.workstreams_fingerprint(p)
    p.write_text("workstreams:\n- id: ws-1")
    f2 = bdb.workstreams_fingerprint(p)
    assert f1 != f2 and f1 and f2


def test_build_db_writes_rows(bdb, tmp_path):
    ws_path = _make_workstreams(
        tmp_path,
        [
            {"id": "ws-1", "adr": "0472", "status": "in_progress", "owner": "claude"},
            {"id": "ws-2", "adr": "0473", "status": "completed", "owner": "platform"},
        ],
    )
    db_path = tmp_path / "build" / "ws.db"
    rc = bdb.write(db_path=db_path, workstreams_path=ws_path)
    assert rc == 0
    assert db_path.is_file()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT id, status FROM workstreams ORDER BY id").fetchall()
        assert rows == [("ws-1", "in_progress"), ("ws-2", "completed")]
    finally:
        conn.close()


def test_build_db_creates_indexes(bdb, tmp_path):
    ws_path = _make_workstreams(tmp_path, [{"id": "ws-1"}])
    db_path = tmp_path / "ws.db"
    bdb.write(db_path=db_path, workstreams_path=ws_path)
    conn = sqlite3.connect(db_path)
    try:
        idx = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        assert "idx_workstreams_status" in idx
        assert "idx_workstreams_adr" in idx
        assert "idx_workstreams_owner" in idx
    finally:
        conn.close()


def test_check_passes_when_fingerprint_matches(bdb, tmp_path):
    ws_path = _make_workstreams(tmp_path, [{"id": "ws-1"}])
    db_path = tmp_path / "ws.db"
    bdb.write(db_path=db_path, workstreams_path=ws_path)
    rc = bdb.check(db_path=db_path, workstreams_path=ws_path)
    assert rc == 0


def test_check_fails_when_yaml_changes(bdb, tmp_path, capsys):
    ws_path = _make_workstreams(tmp_path, [{"id": "ws-1"}])
    db_path = tmp_path / "ws.db"
    bdb.write(db_path=db_path, workstreams_path=ws_path)
    # mutate yaml
    ws_path.write_text(yaml.safe_dump({"workstreams": [{"id": "ws-1"}, {"id": "ws-2"}]}))
    rc = bdb.check(db_path=db_path, workstreams_path=ws_path)
    assert rc == 1
    assert "stale" in capsys.readouterr().err


def test_check_fails_when_db_missing(bdb, tmp_path, capsys):
    ws_path = _make_workstreams(tmp_path, [{"id": "ws-1"}])
    rc = bdb.check(db_path=tmp_path / "missing.db", workstreams_path=ws_path)
    assert rc == 1


def test_query_returns_tsv(bdb, tmp_path, capsys):
    ws_path = _make_workstreams(
        tmp_path,
        [
            {"id": "ws-1", "owner": "claude"},
            {"id": "ws-2", "owner": "claude"},
        ],
    )
    db_path = tmp_path / "ws.db"
    bdb.write(db_path=db_path, workstreams_path=ws_path)
    rc = bdb.query("SELECT id FROM workstreams ORDER BY id", db_path=db_path)
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert lines[0] == "id"
    assert "ws-1" in lines and "ws-2" in lines


def test_query_no_db_returns_2(bdb, tmp_path, capsys):
    rc = bdb.query("SELECT 1", db_path=tmp_path / "missing.db")
    assert rc == 2


def test_main_write_returns_0(bdb, tmp_path):
    ws_path = _make_workstreams(tmp_path, [{"id": "ws-1"}])
    db_path = tmp_path / "ws.db"
    rc = bdb.main(["--workstreams-path", str(ws_path), "--db-path", str(db_path), "--write"])
    assert rc == 0


def test_main_check_returns_0_after_write(bdb, tmp_path):
    ws_path = _make_workstreams(tmp_path, [{"id": "ws-1"}])
    db_path = tmp_path / "ws.db"
    bdb.main(["--workstreams-path", str(ws_path), "--db-path", str(db_path), "--write"])
    rc = bdb.main(["--workstreams-path", str(ws_path), "--db-path", str(db_path), "--check"])
    assert rc == 0


def test_main_query_returns_0(bdb, tmp_path, capsys):
    ws_path = _make_workstreams(tmp_path, [{"id": "ws-1"}])
    db_path = tmp_path / "ws.db"
    bdb.main(["--workstreams-path", str(ws_path), "--db-path", str(db_path), "--write"])
    rc = bdb.main(
        [
            "--workstreams-path",
            str(ws_path),
            "--db-path",
            str(db_path),
            "--query",
            "SELECT id FROM workstreams",
        ]
    )
    assert rc == 0
