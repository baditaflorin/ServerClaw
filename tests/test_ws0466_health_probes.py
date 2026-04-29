"""Tests for ADR 0463 — post-converge / on-demand health probe runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_health_probes.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_health_probes_for_ws0466", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["run_health_probes_for_ws0466"] = module
    spec.loader.exec_module(module)
    return module


def test_run_probe_unknown_kind():
    mod = _load_module()
    ok, detail = mod.run_probe({"kind": "unknown"})
    assert not ok
    assert "unknown" in detail


def test_probe_tcp_open_port(tmp_path):
    """Use an actual listening socket on a free port to verify the TCP probe."""
    import socket as _socket
    import threading

    mod = _load_module()
    server = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(1)

    try:
        # Accept in background to allow the probe to connect cleanly.
        thread = threading.Thread(target=lambda: server.accept(), daemon=True)
        thread.start()
        ok, detail = mod.probe_tcp({"host": "127.0.0.1", "port": port}, timeout=5)
        assert ok, f"unexpected failure: {detail}"
    finally:
        server.close()


def test_probe_tcp_closed_port():
    mod = _load_module()
    # 1 is reserved/likely-closed; if it happens to be open, the test
    # would still confirm the probe distinguishes ok vs error.
    ok, detail = mod.probe_tcp({"host": "127.0.0.1", "port": 1}, timeout=2)
    # Port 1 should be closed → probe returns False.
    assert not ok
    assert "TCP" in detail


def test_probe_http_200(tmp_path):
    """Spin up a tiny HTTP server in-process."""
    import http.server
    import threading

    mod = _load_module()
    handler = http.server.SimpleHTTPRequestHandler
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        ok, detail = mod.probe_http(
            {"url": f"http://127.0.0.1:{port}/", "method": "GET", "expected_status": [200]},
            timeout=5,
        )
        assert ok, detail
    finally:
        server.shutdown()


def test_probe_http_unexpected_status_treated_as_failure():
    """HTTP 404 against a SimpleHTTPRequestHandler with no matching file."""
    import http.server
    import threading

    mod = _load_module()
    handler = http.server.SimpleHTTPRequestHandler
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        ok, _ = mod.probe_http(
            {
                "url": f"http://127.0.0.1:{port}/does-not-exist",
                "method": "GET",
                "expected_status": [200],
            },
            timeout=5,
        )
        assert not ok
    finally:
        server.shutdown()


def test_write_probe_receipt_writes_atomic_json(tmp_path):
    mod = _load_module()
    receipts = tmp_path / "receipts"
    probe = {"kind": "tcp", "host": "127.0.0.1", "port": 12345}
    path = mod.write_probe_receipt(receipts, "alpha", probe, ok=True, detail="OK")
    assert path.is_file()
    payload = json.loads(path.read_text())
    assert payload["service"] == "alpha"
    assert payload["ok"] is True
    assert payload["kind"] == "tcp"
    assert payload["probe"]["port"] == 12345
    assert "probed_at" in payload


def test_main_exits_2_when_no_target():
    mod = _load_module()
    rc = mod.main([])
    assert rc == 2


def test_main_with_unknown_service_returns_failure(tmp_path, capsys):
    mod = _load_module()
    rc = mod.main(["--service", "definitely_not_a_real_service", "--no-receipts"])
    assert rc == 1
