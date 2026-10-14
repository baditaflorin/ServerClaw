"""Certificate-validator CLI contract after ADR 0488's single-deployment model.

ADR 0488 replaced automatic multi-deployment enumeration with an explicitly
selected identity overlay. These tests guard the current CLI and catalog
filtering contract rather than the retired deployment auto-detection path.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_SCRIPT = REPO_ROOT / "scripts" / "certificate_validator.py"


def _load_module(local_root_override: Path):
    spec = importlib.util.spec_from_file_location("cert_validator_for_ws0461", VALIDATOR_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["cert_validator_for_ws0461"] = module
    spec.loader.exec_module(module)
    module.LOCAL_ROOT = local_root_override
    return module


@pytest.fixture
def synthetic_local(tmp_path):
    return tmp_path


def test_help_exposes_single_deployment_validation_options():
    result = subprocess.run(
        ["python3", str(VALIDATOR_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    flat = " ".join(result.stdout.split())
    assert result.returncode == 0
    assert "--check-all" in flat
    assert "--fqdn" in flat
    assert "--all-deployments" not in flat
    assert "--deployment" not in flat


def test_module_imports_cleanly():
    """The validator module imports without side-effects on a fresh
    Python process. Catches AttributeError / NameError introduced by
    refactor."""
    spec = importlib.util.spec_from_file_location("cert_validator_smoke", VALIDATOR_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "_get_real_domain")
    assert hasattr(module, "load_catalog")
    assert hasattr(module, "exclude_retiring_edge_certificates")


def test_certificate_catalog_loader_returns_only_active_entries(tmp_path):
    mod = _load_module(tmp_path)
    catalog = tmp_path / "certificates.json"
    catalog.write_text(
        json.dumps(
            {
                "certificates": [
                    {
                        "service_id": "neko",
                        "status": "active",
                        "endpoint": {
                            "host": "browser.example.com",
                            "port": 443,
                            "server_name": "browser.example.com",
                        },
                    },
                    {
                        "service_id": "retired",
                        "status": "planned",
                        "endpoint": {
                            "host": "old.example.com",
                            "port": 443,
                            "server_name": "old.example.com",
                        },
                    },
                    {
                        "service_id": "private-only",
                        "status": "lan_only",
                        "endpoint": {
                            "host": "private.example.com",
                            "port": 443,
                            "server_name": "private.example.com",
                        },
                    },
                ]
            }
        )
    )

    entries = mod.load_catalog(str(catalog))

    assert [entry["service_id"] for entry in entries] == ["neko"]
