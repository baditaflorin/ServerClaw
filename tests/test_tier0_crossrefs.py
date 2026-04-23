"""Pytest gate for Tier-0 cross-reference validation — ADR 0438.

Fails on any error-severity finding from scripts/validate_tier0_crossrefs.py.
Warning-severity findings are collected and printed but do not fail the suite —
they are tracked as Phase 2/3 work items.

Run directly:
    uvx --python 3.12 --with pyyaml --with jsonschema pytest tests/test_tier0_crossrefs.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_tier0_crossrefs.py"


def _load_validator():
    module_name = "validate_tier0_crossrefs"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec so dataclasses can resolve forward refs.
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def validator():
    return _load_validator()


@pytest.fixture(scope="module")
def tier0(validator):
    return validator.load_tier0()


@pytest.fixture(scope="module")
def all_findings(validator, tier0):
    return validator.run_all_checks(tier0, min_severity="warning")


# ---------------------------------------------------------------------------
# Error-severity gate — fails CI
# ---------------------------------------------------------------------------


def test_no_tier0_errors(all_findings):
    """No Tier-0 check may emit an error-severity finding.

    Errors indicate structural mismatches (missing service_type, postgres client
    referencing unknown service, raw split() in root facts) that would break a
    fork deployment silently.
    """
    errors = [f for f in all_findings if f.severity == "error"]
    if errors:
        lines = [f"  [{f.check_id}] {f.location}: {f.message}" for f in errors]
        pytest.fail(f"{len(errors)} Tier-0 error(s) found — fix before merging:\n" + "\n".join(lines))


# ---------------------------------------------------------------------------
# Individual check gates (one test per check group for granular CI failure)
# ---------------------------------------------------------------------------


def test_A_postgres_clients_all_services_exist(validator, tier0):
    """A1: every postgres client references a known service."""
    findings = validator.check_A1_postgres_services_exist_in_registry(tier0)
    errors = [f for f in findings if f.severity == "error"]
    assert not errors, "\n".join(f"  {f.location}: {f.message}" for f in errors)


def test_C_services_have_host_group_and_type(validator, tier0):
    """C1+C2: every service has host_group and valid service_type."""
    findings = validator.check_C1_host_group_non_empty(tier0) + validator.check_C2_service_type_is_known(tier0)
    errors = [f for f in findings if f.severity == "error"]
    assert not errors, "\n".join(f"  {f.location}: {f.message}" for f in errors)


def test_E_no_raw_splits_in_tier0(validator, tier0):
    """E1+E2: no raw platform_domain splits in service registry or postgres clients."""
    findings = validator.check_E1_no_raw_split_in_service_registry(
        tier0
    ) + validator.check_E2_no_raw_split_in_postgres_clients(tier0)
    errors = [f for f in findings if f.severity == "error"]
    assert not errors, "\n".join(f"  {f.location}: {f.message}" for f in errors)


def test_F_scope_playbooks_exist(validator, tier0):
    """F1: every playbook in execution scopes exists on disk."""
    findings = validator.check_F1_scope_playbooks_exist(tier0)
    errors = [f for f in findings if f.severity == "error"]
    assert not errors, "\n".join(f"  {f.location}: {f.message}" for f in errors)


# ---------------------------------------------------------------------------
# Warning inventory (informational — helps track Phase 2/3 progress)
# ---------------------------------------------------------------------------


def test_warning_count_does_not_regress(all_findings):
    """Warning count must not increase above the Phase-1 baseline.

    This is a regression gate: adding new hardcoded-prefix callsites
    bumps the count and fails CI. Reducing it (Phase 2/3 sweeps) passes fine.

    Update the BASELINE constant after each successful phase sweep.
    """
    BASELINE = 0  # Phase-2a sweep: all /etc/lv3/ paths parameterized in platform_postgres.yml
    warnings = [f for f in all_findings if f.severity == "warning"]
    assert len(warnings) <= BASELINE, (
        f"Warning count {len(warnings)} exceeds Phase-1 baseline {BASELINE}. "
        f"A new hardcoded-prefix callsite was introduced — address it or raise the "
        f"baseline in tests/test_tier0_crossrefs.py with a comment explaining why."
    )
