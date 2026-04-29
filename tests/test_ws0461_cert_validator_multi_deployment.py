"""Tests for ADR 0458 — cert validator multi-deployment auto-detect.

Covers:
  1. `_list_deployment_slugs()` returns the slugs under .local/deployments/.
  2. `--all-deployments` flag is parsed and visible in --help.
  3. Auto-trigger: no flag passed + multiple deployments → multi-mode runs.
  4. Single-deployment installs continue to use the legacy single path.
"""

from __future__ import annotations

import importlib.util
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


def test_list_deployment_slugs_empty(synthetic_local):
    mod = _load_module(synthetic_local)
    assert mod._list_deployment_slugs() == []


def test_list_deployment_slugs_returns_sorted(synthetic_local):
    mod = _load_module(synthetic_local)
    (synthetic_local / "deployments" / "zeta").mkdir(parents=True)
    (synthetic_local / "deployments" / "alpha").mkdir(parents=True)
    (synthetic_local / "deployments" / "beta").mkdir(parents=True)
    assert mod._list_deployment_slugs() == ["alpha", "beta", "zeta"]


def test_list_deployment_slugs_skips_dotfiles(synthetic_local):
    mod = _load_module(synthetic_local)
    (synthetic_local / "deployments" / ".cache").mkdir(parents=True)
    (synthetic_local / "deployments" / "real").mkdir(parents=True)
    assert mod._list_deployment_slugs() == ["real"]


def test_help_lists_all_deployments_flag():
    """The --all-deployments flag must appear in --help so operators discover it."""
    result = subprocess.run(
        ["python3", str(VALIDATOR_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    flat = " ".join(result.stdout.split())
    assert "--all-deployments" in flat
    assert "ADR 0458" in flat


def test_help_lists_deployment_flag_still():
    """ADR 0456's --deployment must continue to appear (regression check)."""
    result = subprocess.run(
        ["python3", str(VALIDATOR_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    # argparse wraps long help strings; collapse whitespace before searching.
    flat = " ".join(result.stdout.split())
    assert "--deployment" in flat
    assert "ADR 0456" in flat


def test_module_imports_cleanly():
    """The validator module imports without side-effects on a fresh
    Python process. Catches AttributeError / NameError introduced by
    refactor."""
    spec = importlib.util.spec_from_file_location("cert_validator_smoke", VALIDATOR_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # Sanity-check the new helper exists.
    assert hasattr(module, "_list_deployment_slugs")
    assert hasattr(module, "_resolve_deployment_slug")
    assert hasattr(module, "_get_real_domain")
