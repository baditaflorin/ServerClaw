"""Tests for ADR 0464 — ssh_with_retry classifier + backoff."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ssh_with_retry.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ssh_with_retry_for_ws0467", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["ssh_with_retry_for_ws0467"] = module
    spec.loader.exec_module(module)
    return module


# --- classifier ------------------------------------------------------------


@pytest.mark.parametrize(
    "stderr,expected",
    [
        ("Permission denied (publickey).", "auth_failure"),
        ("Authentication failed for user", "auth_failure"),
        ("Connection timed out during banner exchange", "banner_timeout"),
        ("Connection to UNKNOWN port 65535 timed out", "banner_timeout"),
        ("ssh: connect to host x port 22: Connection refused", "connection_refused"),
        ("ssh: Could not resolve hostname unknown.invalid", "dns_failure"),
        ("Name or service not known", "dns_failure"),
        ("ssh: connect to host: No route to host", "network_partition"),
        ("Network is unreachable", "network_partition"),
        ("REMOTE HOST IDENTIFICATION HAS CHANGED!", "host_key_mismatch"),
        ("", "unknown"),
        ("some weird error nobody saw before", "unknown"),
    ],
)
def test_classifier(stderr, expected):
    mod = _load_module()
    assert mod.classify_ssh_stderr(stderr) == expected


# --- backoff ---------------------------------------------------------------


def test_compute_backoff_no_jitter_deterministic():
    mod = _load_module()
    # base=1, max=10
    assert mod.compute_backoff(1, 1.0, 10.0, jitter=False) == 1.0
    assert mod.compute_backoff(2, 1.0, 10.0, jitter=False) == 2.0
    assert mod.compute_backoff(3, 1.0, 10.0, jitter=False) == 4.0
    assert mod.compute_backoff(4, 1.0, 10.0, jitter=False) == 8.0
    # capped at max
    assert mod.compute_backoff(5, 1.0, 10.0, jitter=False) == 10.0
    assert mod.compute_backoff(10, 1.0, 10.0, jitter=False) == 10.0


def test_compute_backoff_with_jitter_within_bounds():
    mod = _load_module()
    for _ in range(20):
        delay = mod.compute_backoff(2, 2.0, 100.0, jitter=True)
        # jitter range is 0.5*base to 1.5*base of the no-jitter value (4.0)
        assert 2.0 <= delay <= 6.0


# --- receipt write ---------------------------------------------------------


def test_write_failure_receipt_atomic(tmp_path):
    mod = _load_module()
    attempts = [
        {"attempt": 1, "exit_code": 255, "classification": "banner_timeout", "stderr_excerpt": "..."},
        {"attempt": 2, "exit_code": 0, "classification": "unknown", "stderr_excerpt": ""},
    ]
    path = mod.write_failure_receipt(
        tmp_path / "receipts",
        target="ops@10.10.10.10",
        attempts=attempts,
        final_outcome="success",
    )
    assert path.is_file()
    payload = json.loads(path.read_text())
    assert payload["target"] == "ops@10.10.10.10"
    assert payload["final_outcome"] == "success"
    assert len(payload["attempts"]) == 2


# --- target extraction -----------------------------------------------------


@pytest.mark.parametrize(
    "args,expected",
    [
        (["-i", "key", "ops@host.example", "uname"], "ops@host.example"),
        (["-p", "22", "host", "uname"], "host"),
        (["-vvv"], "unknown"),
        ([], "unknown"),
    ],
)
def test_extract_target(args, expected):
    mod = _load_module()
    assert mod._extract_target(args) == expected


# --- main exit codes -------------------------------------------------------


def test_main_no_args_returns_2():
    mod = _load_module()
    rc = mod.main([])
    assert rc == 2


def test_main_invalid_retries_returns_2():
    mod = _load_module()
    rc = mod.main(["--retries", "0", "--", "host"])
    assert rc == 2
