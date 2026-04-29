"""Tests for ADR 0468 — pre-converge snapshot."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "preconverge_snapshot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("preconverge_snapshot_for_ws0470", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["preconverge_snapshot_for_ws0470"] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload))
    return path


def test_compose_writes_receipt(tmp_path):
    mod = _load_module()
    units = _write_json(tmp_path / "units.json", [{"unit": "nginx.service", "load": "loaded", "active": "active", "sub": "running"}])
    containers = _write_json(tmp_path / "containers.json", [{"name": "ops-portal", "image": "lv3-ops-portal:latest", "status": "Up 2 hours"}])
    files = _write_json(tmp_path / "files.json", [{"path": "/etc/nginx/sites-available/lv3-edge.conf", "sha256": "abc", "size_bytes": 1234}])
    receipts_dir = tmp_path / "receipts"
    rc = mod.main(
        [
            "compose",
            "--run-id", "test-run-1",
            "--host", "nginx",
            "--role", "nginx_edge_publication",
            "--systemd-units-json", str(units),
            "--docker-containers-json", str(containers),
            "--managed-files-json", str(files),
            "--receipts-dir", str(receipts_dir),
        ]
    )
    assert rc == 0
    receipts = list(receipts_dir.iterdir())
    assert len(receipts) == 1
    payload = json.loads(receipts[0].read_text())
    assert payload["host"] == "nginx"
    assert payload["run_id"] == "test-run-1"
    assert payload["role"] == "nginx_edge_publication"
    assert len(payload["systemd_units"]) == 1
    assert len(payload["docker_containers"]) == 1
    assert len(payload["managed_files"]) == 1


def test_compose_handles_missing_input_files(tmp_path):
    """Missing input files should still produce a receipt with empty arrays."""
    mod = _load_module()
    receipts_dir = tmp_path / "receipts"
    rc = mod.main(
        [
            "compose",
            "--run-id", "test-run-2",
            "--host", "nginx",
            "--role", "nginx_edge_publication",
            "--systemd-units-json", str(tmp_path / "missing1.json"),
            "--docker-containers-json", str(tmp_path / "missing2.json"),
            "--managed-files-json", str(tmp_path / "missing3.json"),
            "--receipts-dir", str(receipts_dir),
        ]
    )
    assert rc == 0
    receipts = list(receipts_dir.iterdir())
    assert len(receipts) == 1
    payload = json.loads(receipts[0].read_text())
    assert payload["systemd_units"] == []


def test_inspect_by_host(tmp_path, capsys):
    mod = _load_module()
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    payload = {
        "schema_version": "1.0.0",
        "host": "nginx",
        "run_id": "abc",
        "role": "nginx_edge_publication",
        "captured_at": "2026-04-29T00:00:00+00:00",
        "systemd_units": [{}],
        "docker_containers": [],
        "managed_files": [{}, {}],
    }
    (receipts_dir / "nginx-abc.json").write_text(json.dumps(payload))
    rc = mod.main(["inspect", "--host", "nginx", "--receipts-dir", str(receipts_dir)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "nginx-abc.json" in captured.out
    assert "managed_files=2" in captured.out


def test_inspect_returns_1_on_no_match(tmp_path):
    mod = _load_module()
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir()
    rc = mod.main(["inspect", "--host", "missing-host", "--receipts-dir", str(receipts_dir)])
    assert rc == 1


def test_inspect_requires_path_or_host(tmp_path):
    mod = _load_module()
    rc = mod.main(["inspect", "--receipts-dir", str(tmp_path / "x")])
    assert rc == 2
