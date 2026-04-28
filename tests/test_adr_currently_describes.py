"""Unit tests for the currently_describes mapping — ADR 0447 item 17.

implementation_status answers "where is this ADR in its lifecycle?";
currently_describes answers "what kind of state should an LLM treat
this ADR's content as?". Pinning the mapping in tests forces a future
status-vocabulary expansion to update both the lookup and the test, so
new statuses cannot silently fall through to the fallback value.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "adr_discovery.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("adr_discovery_for_447", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["adr_discovery_for_447"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ad():
    return _load_module()


@pytest.mark.parametrize(
    "status,expected",
    [
        ("Implemented", "current_state"),
        ("Accepted", "current_state"),
        ("Partial", "mixed_state"),
        ("Proposed", "goal_state"),
        ("Not Implemented", "goal_state"),
        ("Deprecated", "historical"),
    ],
)
def test_currently_describes_canonical_mapping(ad, status, expected):
    """Every status in IMPLEMENTATION_STATUS_ORDER must map to a
    `currently_describes` value. If a future PR adds a new status to
    IMPLEMENTATION_STATUS_ORDER without updating
    CURRENTLY_DESCRIBES_BY_STATUS, the test below
    (`test_every_implementation_status_is_mapped`) catches it."""
    assert ad.currently_describes_for(status) == expected


def test_every_implementation_status_is_mapped(ad):
    """Forces a status-vocabulary expansion to update both sides.

    Without this assertion a new status (e.g. `Superseded`) would
    silently default to the fallback value, hiding the LLM-context drift
    the field exists to prevent.
    """
    unmapped = [s for s in ad.IMPLEMENTATION_STATUS_ORDER if s not in ad.CURRENTLY_DESCRIBES_BY_STATUS]
    assert not unmapped, (
        f"new implementation_status values are not mapped to "
        f"currently_describes: {unmapped}. Add them to "
        f"CURRENTLY_DESCRIBES_BY_STATUS."
    )


def test_unknown_status_returns_fallback(ad):
    """An unmapped status must return the fallback literal — surfaces
    the gap rather than silently labelling unknown statuses as
    `current_state`. If callers want strict mode they can compare
    against ad.CURRENTLY_DESCRIBES_FALLBACK."""
    assert ad.currently_describes_for("MintCondition") == ad.CURRENTLY_DESCRIBES_FALLBACK
    assert ad.CURRENTLY_DESCRIBES_FALLBACK == "unknown"


def test_to_entry_carries_currently_describes(ad):
    meta = ad.AdrMeta(
        number="0447",
        title="Phase 3",
        status="Proposed",
        implementation_status="Proposed",
        implemented_in_repo_version=None,
        implemented_in_platform_version=None,
        implemented_on=None,
        date="2026-04-28",
        concern="llm",
        keywords=["llm"],
        summary="...",
        filename="0447-phase3.md",
        path="docs/adr/0447-phase3.md",
    )
    entry = meta.to_entry()
    assert entry["currently_describes"] == "goal_state"


def test_to_compact_entry_carries_currently_describes(ad):
    meta = ad.AdrMeta(
        number="0443",
        title="Topology Reconciler",
        status="Accepted",
        implementation_status="Implemented",
        implemented_in_repo_version="0.179.0",
        implemented_in_platform_version=None,
        implemented_on="2026-04-27",
        date="2026-04-27",
        concern="drift",
        keywords=["drift"],
        summary="...",
        filename="0443-x.md",
        path="docs/adr/0443-x.md",
    )
    entry = meta.to_compact_entry()
    assert entry["currently_describes"] == "current_state"


def test_currently_describes_property_matches_helper(ad):
    """The dataclass property and the module-level helper must agree —
    no drift between the two surfaces."""
    meta = ad.AdrMeta(
        number="0001",
        title="x",
        status="Proposed",
        implementation_status="Partial",
        implemented_in_repo_version=None,
        implemented_in_platform_version=None,
        implemented_on=None,
        date="2026-01-01",
        concern="x",
        keywords=[],
        summary="x",
        filename="x.md",
        path="x.md",
    )
    assert meta.currently_describes == ad.currently_describes_for("Partial") == "mixed_state"
