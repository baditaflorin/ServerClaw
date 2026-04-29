"""Tests for ADR 0466 — converge state diff receipts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "converge_state_receipt.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("converge_state_receipt_for_ws0468", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["converge_state_receipt_for_ws0468"] = module
    spec.loader.exec_module(module)
    return module


def test_file_snapshot_existing(tmp_path):
    mod = _load_module()
    target = tmp_path / "f.txt"
    target.write_text("hello world")
    snap = mod.file_snapshot(target)
    assert snap["path"] == str(target)
    assert "sha256" in snap
    assert snap["size_bytes"] == 11


def test_file_snapshot_missing(tmp_path):
    mod = _load_module()
    snap = mod.file_snapshot(tmp_path / "nope.txt")
    assert snap["missing"] is True


def test_diff_snapshots_detects_change(tmp_path):
    mod = _load_module()
    before = [{"path": "/x", "sha256": "aaa", "size_bytes": 3}]
    after = [{"path": "/x", "sha256": "bbb", "size_bytes": 4}]
    diff = mod.diff_snapshots(before, after)
    assert len(diff) == 1
    assert diff[0]["changed"] is True
    assert diff[0]["before_sha256"] == "aaa"
    assert diff[0]["after_sha256"] == "bbb"


def test_diff_snapshots_unchanged(tmp_path):
    mod = _load_module()
    before = [{"path": "/x", "sha256": "aaa", "size_bytes": 3}]
    after = [{"path": "/x", "sha256": "aaa", "size_bytes": 3}]
    diff = mod.diff_snapshots(before, after)
    assert diff[0]["changed"] is False


def test_diff_snapshots_handles_path_added(tmp_path):
    mod = _load_module()
    before = []
    after = [{"path": "/new", "sha256": "n", "size_bytes": 1}]
    diff = mod.diff_snapshots(before, after)
    assert diff[0]["before_missing"] is True
    assert diff[0]["after_missing"] is False
    assert diff[0]["changed"] is True


def test_diff_snapshots_handles_path_removed(tmp_path):
    mod = _load_module()
    before = [{"path": "/old", "sha256": "o", "size_bytes": 1}]
    after = []
    diff = mod.diff_snapshots(before, after)
    assert diff[0]["after_missing"] is True
    assert diff[0]["changed"] is True


def test_write_state_receipt_atomic(tmp_path):
    mod = _load_module()
    receipts_dir = tmp_path / "receipts"
    files = [
        {"path": "/etc/foo.conf", "before_sha256": "a", "after_sha256": "b", "changed": True},
    ]
    path = mod.write_state_receipt(
        receipts_dir,
        run_id="run-123",
        host="nginx",
        role="nginx_edge_publication",
        files=files,
        handlers_fired=["reload nginx"],
        handlers_notified_but_skipped=[],
    )
    assert path.is_file()
    payload = json.loads(path.read_text())
    assert payload["run_id"] == "run-123"
    assert payload["host"] == "nginx"
    assert payload["role"] == "nginx_edge_publication"
    assert payload["summary"]["files_changed"] == 1
    assert payload["summary"]["handlers_fired"] == 1


def test_cli_snapshot_subcommand(tmp_path, capsys):
    mod = _load_module()
    f = tmp_path / "x.txt"
    f.write_text("hello")
    rc = mod.main(["snapshot", str(f)])
    assert rc == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert isinstance(parsed, list)
    assert parsed[0]["path"] == str(f)
    assert parsed[0]["size_bytes"] == 5


def test_cli_write_receipt_end_to_end(tmp_path):
    mod = _load_module()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps([{"path": "/a", "sha256": "1", "size_bytes": 1}]))
    after.write_text(json.dumps([{"path": "/a", "sha256": "2", "size_bytes": 2}]))
    receipts_dir = tmp_path / "receipts"
    rc = mod.main(
        [
            "write-receipt",
            "--run-id",
            "run-456",
            "--host",
            "h1",
            "--role",
            "r1",
            "--before",
            str(before),
            "--after",
            str(after),
            "--handlers-fired",
            "reload nginx,restart oauth2-proxy",
            "--receipts-dir",
            str(receipts_dir),
        ]
    )
    assert rc == 0
    receipts = list(receipts_dir.iterdir())
    assert len(receipts) == 1
    payload = json.loads(receipts[0].read_text())
    assert payload["summary"]["files_changed"] == 1
    assert payload["handlers_fired"] == ["reload nginx", "restart oauth2-proxy"]
