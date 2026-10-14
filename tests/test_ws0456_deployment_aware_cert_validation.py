"""Tests for ADR 0456 — certificate validation with an explicit identity overlay."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_SCRIPT = REPO_ROOT / "scripts" / "certificate_validator.py"
GATE_BYPASS_CATALOG = REPO_ROOT / "config" / "gate-bypass-waiver-catalog.json"


def _load_validator_module(local_root_override: Path):
    spec = importlib.util.spec_from_file_location("cert_validator_for_ws0456", VALIDATOR_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["cert_validator_for_ws0456"] = module
    spec.loader.exec_module(module)
    module.LOCAL_ROOT = local_root_override
    return module


@pytest.fixture
def synthetic_local(tmp_path):
    (tmp_path / "deployments" / "alpha").mkdir(parents=True)
    (tmp_path / "deployments" / "beta").mkdir(parents=True)
    return tmp_path


def _write_identity(path: Path, domain: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"platform_domain: {domain}\n")


def test_get_real_domain_prefers_explicit_overlay(synthetic_local, monkeypatch):
    mod = _load_validator_module(synthetic_local)
    monkeypatch.delenv("PLATFORM_IDENTITY_OVERLAY", raising=False)
    legacy_identity = synthetic_local / "identity.yml"
    selected_identity = synthetic_local / "deployments" / "alpha" / "identity.yml"
    _write_identity(legacy_identity, "legacy.example")
    _write_identity(selected_identity, "alpha.example")
    monkeypatch.setenv("PLATFORM_IDENTITY_OVERLAY", str(selected_identity))

    assert mod._get_real_domain() == "alpha.example"


def test_get_real_domain_falls_back_to_legacy_overlay(synthetic_local, monkeypatch):
    mod = _load_validator_module(synthetic_local)
    monkeypatch.delenv("PLATFORM_IDENTITY_OVERLAY", raising=False)
    _write_identity(synthetic_local / "identity.yml", "legacy.example")
    assert mod._get_real_domain() == "legacy.example"


def test_get_real_domain_skips_generic_placeholder(synthetic_local, monkeypatch):
    mod = _load_validator_module(synthetic_local)
    identity = synthetic_local / "deployments" / "alpha" / "identity.yml"
    _write_identity(identity, "example.com")
    monkeypatch.setenv("PLATFORM_IDENTITY_OVERLAY", str(identity))

    assert mod._get_real_domain() is None


def test_get_real_domain_returns_none_for_missing_selected_overlay(synthetic_local, monkeypatch):
    mod = _load_validator_module(synthetic_local)
    monkeypatch.setenv("PLATFORM_IDENTITY_OVERLAY", str(synthetic_local / "missing.yml"))

    assert mod._get_real_domain() is None


def test_cross_deployment_drift_reason_allows_skip_cert_validation():
    catalog = json.loads(GATE_BYPASS_CATALOG.read_text())
    reason = catalog["reason_codes"].get("cross_deployment_drift")
    assert reason is not None
    assert "skip_cert_validation" in reason["allowed_bypasses"]


def test_cross_deployment_drift_has_finite_expiry():
    catalog = json.loads(GATE_BYPASS_CATALOG.read_text())
    reason = catalog["reason_codes"]["cross_deployment_drift"]
    assert 1 <= reason["max_expiry_days"] <= 7
