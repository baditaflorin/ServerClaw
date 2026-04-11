"""Platform reconciliation library (ADR 0394 Phase 1).

Provides core primitives for detecting portal drift, regenerating artifacts,
and validating freshness across all platform portals.

Usage::

    from scripts.reconciliation.core import (
        detect_portal_drift,
        reconcile_all_portals,
        regenerate_portal,
        validate_all_artifacts,
    )
"""

from __future__ import annotations

__all__ = [
    "detect_portal_drift",
    "reconcile_all_portals",
    "regenerate_portal",
    "validate_all_artifacts",
]


def __getattr__(name: str):
    """Lazy re-export from core to avoid heavyweight imports at package load."""
    if name in __all__:
        from scripts.reconciliation.core import (
            detect_portal_drift,
            reconcile_all_portals,
            regenerate_portal,
            validate_all_artifacts,
        )

        _exports = {
            "detect_portal_drift": detect_portal_drift,
            "reconcile_all_portals": reconcile_all_portals,
            "regenerate_portal": regenerate_portal,
            "validate_all_artifacts": validate_all_artifacts,
        }
        return _exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
