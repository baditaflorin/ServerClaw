"""Tests for ADR 0456 — deployment-aware certificate validation."""

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


def _write_identity(local_root: Path, slug: str | None, domain: str) -> None:
    if slug:
        path = local_root / "deployments" / slug / "identity.yml"
    else:
        path = local_root / "identity.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"platform_domain: {domain}\n")


def test_resolve_explicit_wins(synthetic_local, monkeypatch):
    mod = _load_validator_module(synthetic_local)
    monkeypatch.setenv("DEPLOYMENT", "from_env")
    assert mod._resolve_deployment_slug("from_explicit") == "from_explicit"


def test_resolve_falls_back_to_env(synthetic_local, monkeypatch):
    mod = _load_validator_module(synthetic_local)
    monkeypatch.setenv("DEPLOYMENT", "from_env")
    assert mod._resolve_deployment_slug(None) == "from_env"


def test_resolve_falls_back_to_active_file(synthetic_local, monkeypatch):
    mod = _load_validator_module(synthetic_local)
    monkeypatch.delenv("DEPLOYMENT", raising=False)
    (synthetic_local / "active-deployment").write_text("from_file\n")
    assert mod._resolve_deployment_slug(None) == "from_file"


def test_resolve_returns_none_when_unset(synthetic_local, monkeypatch):
    mod = _load_validator_module(synthetic_local)
    monkeypatch.delenv("DEPLOYMENT", raising=False)
    assert mod._resolve_deployment_slug(None) is None


def test_get_real_domain_reads_per_deployment_identity(synthetic_local):
    mod = _load_validator_module(synthetic_local)
    _write_identity(synthetic_local, "alpha", "alpha.example")
    assert mod._get_real_domain(deployment_slug="alpha") == "alpha.example"


def test_get_real_domain_returns_none_when_per_deployment_missing(synthetic_local):
    mod = _load_validator_module(synthetic_local)
    assert mod._get_real_domain(deployment_slug="missing") is None


def test_get_real_domain_skips_example_com_in_per_deployment(synthetic_local):
    mod = _load_validator_module(synthetic_local)
    _write_identity(synthetic_local, "alpha", "example.com")
    assert mod._get_real_domain(deployment_slug="alpha") is None


def test_get_real_domain_falls_back_to_legacy_overlay(synthetic_local):
    mod = _load_validator_module(synthetic_local)
    _write_identity(synthetic_local, None, "legacy.example")
    assert mod._get_real_domain() == "legacy.example"


def test_get_real_domain_per_deployment_overrides_legacy(synthetic_local):
    mod = _load_validator_module(synthetic_local)
    _write_identity(synthetic_local, None, "legacy.example")
    _write_identity(synthetic_local, "beta", "beta.example")
    assert mod._get_real_domain(deployment_slug="beta") == "beta.example"
    assert mod._get_real_domain() == "legacy.example"


def test_cross_deployment_drift_reason_allows_skip_cert_validation():
    catalog = json.loads(GATE_BYPASS_CATALOG.read_text())
    reason = catalog["reason_codes"].get("cross_deployment_drift")
    assert reason is not None
    assert "skip_cert_validation" in reason["allowed_bypasses"]


def test_cross_deployment_drift_has_finite_expiry():
    catalog = json.loads(GATE_BYPASS_CATALOG.read_text())
    reason = catalog["reason_codes"]["cross_deployment_drift"]
    assert 1 <= reason["max_expiry_days"] <= 7
