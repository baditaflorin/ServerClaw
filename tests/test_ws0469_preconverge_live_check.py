"""Tests for ADR 0467 — pre-converge live cert + DNS check."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "preconverge_live_check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("preconverge_live_check_for_ws0469", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["preconverge_live_check_for_ws0469"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "fqdn,sans,expected",
    [
        ("ops.example.org", ["ops.example.org"], True),
        ("ops.example.org", ["*.example.org"], True),
        ("nested.api.example.org", ["*.example.org"], False),  # wildcard one-level only
        ("ops.example.org", ["other.example"], False),
        ("Ops.0Fork.com", ["ops.example.org"], True),  # case-insensitive
        ("ops.example.org", [], False),
    ],
)
def test_san_covers(fqdn, sans, expected):
    mod = _load_module()
    assert mod.san_covers(fqdn, sans) is expected


def test_check_dns_resolves_localhost():
    mod = _load_module()
    result = mod.check_dns("localhost")
    assert result["ok"] is True
    assert result["resolved"] in ("127.0.0.1", "::1")


def test_check_dns_unknown_host():
    mod = _load_module()
    result = mod.check_dns("definitely-not-a-real-host-12345.invalid")
    assert result["ok"] is False
    assert "resolution failed" in result["detail"]


def test_check_dns_expected_ip_match():
    mod = _load_module()
    result = mod.check_dns("localhost", expected_ips=["127.0.0.1"])
    if result["resolved"] == "127.0.0.1":
        assert result["ok"] is True
    else:
        # On systems where localhost resolves to ::1 first.
        assert result["ok"] is False


def test_check_dns_expected_ip_mismatch():
    mod = _load_module()
    result = mod.check_dns("localhost", expected_ips=["198.51.100.1"])
    assert result["ok"] is False
    assert "not in expected" in result["detail"]


def test_main_no_args_returns_2():
    mod = _load_module()
    rc = mod.main([])
    assert rc == 2
