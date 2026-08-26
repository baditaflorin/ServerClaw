"""Unit tests for scripts/capacity_probe.py — ADR 0482.

Covers the pure probe-output parser. The SSH transport (probe_via_ssh)
is exercised only indirectly via integration tests because it shells out
to ssh; the parser is what carries the load-bearing logic and must be
deterministic.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

spec = importlib.util.spec_from_file_location("capacity_probe", SCRIPTS_DIR / "capacity_probe.py")
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(probe)


def test_parse_minimal_output():
    raw = "ram_total_mb=4096\ncores=2\nthreads=4\n"
    result = probe._parse_probe_output(raw)
    assert result["schema_version"] == 1
    assert result["probed_via"] == "ssh"
    assert result["host"]["ram_total_mb"] == 4096
    assert result["host"]["cores"] == 2
    assert result["host"]["threads"] == 4
    assert result["host"]["ram_reserved_mb"] == 4096  # default applied
    assert result["host"]["storage"] == []
    assert result["host"]["capabilities"] == []


def test_parse_full_output_with_storage_and_caps():
    raw = """
ram_total_mb=65536
cores=16
threads=32
storage=local|zfs|1024|800
storage=local-lvm|lvm|2048|1500
cap=nvme
cap=gpu
public_ipv4=203.0.113.3
"""
    result = probe._parse_probe_output(raw)
    h = result["host"]
    assert h["ram_total_mb"] == 65536
    assert h["cores"] == 16
    assert h["threads"] == 32
    assert h["capabilities"] == ["nvme", "gpu"]
    assert h["networks"]["public_ipv4"] == "203.0.113.3"
    assert len(h["storage"]) == 2
    assert h["storage"][0] == {"name": "local", "type": "zfs", "total_gb": 1024, "free_gb": 800}
    assert h["storage"][1] == {"name": "local-lvm", "type": "lvm", "total_gb": 2048, "free_gb": 1500}


def test_parse_normalizes_unknown_storage_type_to_other():
    raw = "ram_total_mb=4096\ncores=2\nthreads=2\nstorage=weird|exotica|10|5\n"
    result = probe._parse_probe_output(raw)
    assert result["host"]["storage"][0]["type"] == "other"


def test_parse_skips_malformed_storage_lines():
    raw = "ram_total_mb=4096\ncores=1\nthreads=1\nstorage=incomplete|line\n"
    result = probe._parse_probe_output(raw)
    assert result["host"]["storage"] == []  # not enough fields → skipped


def test_parse_ignores_blank_and_unrecognized_lines():
    raw = "\n\nrandom_garbage\nram_total_mb=2048\nweird=value\ncores=1\nthreads=1\n"
    result = probe._parse_probe_output(raw)
    assert result["host"]["ram_total_mb"] == 2048


def test_validate_accepts_well_formed_capacity():
    capacity = {
        "schema_version": 1,
        "probed_at": "2026-05-12T00:00:00Z",
        "probed_via": "operator",
        "host": {"ram_total_mb": 8192, "cores": 4, "threads": 8},
    }
    errs = probe.validate(capacity)
    assert errs == []


def test_validate_rejects_missing_ram_total_mb():
    capacity = {
        "schema_version": 1,
        "probed_at": "2026-05-12T00:00:00Z",
        "probed_via": "operator",
        "host": {"cores": 4},
    }
    errs = probe.validate(capacity)
    assert errs, "expected validation errors for missing ram_total_mb"


def test_validate_rejects_wrong_schema_version():
    capacity = {
        "schema_version": 2,
        "probed_at": "2026-05-12T00:00:00Z",
        "probed_via": "operator",
        "host": {"ram_total_mb": 8192, "cores": 4},
    }
    errs = probe.validate(capacity)
    assert errs


def test_validate_rejects_too_small_ram():
    """Schema requires ram_total_mb >= 1024."""
    capacity = {
        "schema_version": 1,
        "probed_at": "2026-05-12T00:00:00Z",
        "probed_via": "operator",
        "host": {"ram_total_mb": 512, "cores": 1},
    }
    errs = probe.validate(capacity)
    assert errs
