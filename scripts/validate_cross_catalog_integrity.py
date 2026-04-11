#!/usr/bin/env python3
"""Validate referential integrity across platform catalogs.

Catches stale references that individual catalog validators miss because each
catalog is validated in isolation. Examples of bugs this finds:

  - A service removed from the dependency graph but still referenced in the
    health-probe catalog → probe will silently fail with an unknown service.
  - An API gateway route pointing at a service that no longer exists → gateway
    will return 502 with no obvious cause.
  - A secret whose owner_service was renamed → rotation scripts target a phantom
    service.
  - Gate bypass waivers for reason codes that have been removed from the catalog.

Run via:
    python scripts/validate_cross_catalog_integrity.py
    make validate-cross-catalog
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from controller_automation_toolkit import emit_cli_error


# ---------------------------------------------------------------------------
# Catalog paths
# ---------------------------------------------------------------------------

DEPENDENCY_GRAPH_PATH = REPO_ROOT / "config" / "dependency-graph.json"
HEALTH_PROBE_CATALOG_PATH = REPO_ROOT / "config" / "health-probe-catalog.json"
API_GATEWAY_CATALOG_PATH = REPO_ROOT / "config" / "api-gateway-catalog.json"
SECRET_CATALOG_PATH = REPO_ROOT / "config" / "secret-catalog.json"
GATE_BYPASS_WAIVER_CATALOG_PATH = REPO_ROOT / "config" / "gate-bypass-waiver-catalog.json"
GATE_BYPASS_RECEIPT_DIR = REPO_ROOT / "receipts" / "gate-bypasses"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    check: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.path}: {self.message}"


@dataclass
class IntegrityReport:
    violations: list[Violation] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0

    def add_violation(self, check: str, path: str, message: str) -> None:
        self.violations.append(Violation(check=check, path=path, message=message))

    def mark_ran(self, check: str) -> None:
        self.checks_run.append(check)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dep_graph_node_ids(graph: dict[str, Any]) -> frozenset[str]:
    """Return the set of all node IDs from the dependency graph."""
    return frozenset(node["id"] for node in graph.get("nodes", []) if "id" in node)


# ---------------------------------------------------------------------------
# Check 1: health-probe-catalog → dependency-graph
# ---------------------------------------------------------------------------


def check_health_probe_services(report: IntegrityReport) -> None:
    """Every service key in health-probe-catalog must be a known dep-graph node ID."""
    check = "health-probe→dep-graph"
    report.mark_ran(check)

    graph = _load_json(DEPENDENCY_GRAPH_PATH)
    known = _dep_graph_node_ids(graph)

    catalog = _load_json(HEALTH_PROBE_CATALOG_PATH)
    probe_services: dict[str, Any] = catalog.get("services", {})

    for service_id in sorted(probe_services):
        if service_id not in known:
            report.add_violation(
                check,
                f"config/health-probe-catalog.json#/services/{service_id}",
                f"probe service '{service_id}' is not a node in the dependency graph — "
                "it was likely removed or renamed; the probe will silently target a phantom service",
            )


# ---------------------------------------------------------------------------
# Check 2: api-gateway-catalog → dependency-graph
# ---------------------------------------------------------------------------


def check_api_gateway_services(report: IntegrityReport) -> None:
    """Every gateway route id in api-gateway-catalog must be a known dep-graph node ID."""
    check = "api-gateway→dep-graph"
    report.mark_ran(check)

    graph = _load_json(DEPENDENCY_GRAPH_PATH)
    known = _dep_graph_node_ids(graph)

    catalog = _load_json(API_GATEWAY_CATALOG_PATH)
    gateway_services: list[dict[str, Any]] = catalog.get("services", [])

    for entry in gateway_services:
        service_id = entry.get("id", "")
        if not service_id:
            continue
        if service_id not in known:
            report.add_violation(
                check,
                f"config/api-gateway-catalog.json#/services[id={service_id!r}]",
                f"gateway route '{service_id}' is not a node in the dependency graph — "
                "route will proxy to an undefined upstream, causing 502 errors",
            )


# ---------------------------------------------------------------------------
# Check 3: secret-catalog → dependency-graph
# ---------------------------------------------------------------------------


def check_secret_owner_services(report: IntegrityReport) -> None:
    """Every secret's owner_service must be a known dep-graph node ID."""
    check = "secret-catalog→dep-graph"
    report.mark_ran(check)

    graph = _load_json(DEPENDENCY_GRAPH_PATH)
    known = _dep_graph_node_ids(graph)

    catalog = _load_json(SECRET_CATALOG_PATH)
    secrets: list[dict[str, Any]] = catalog.get("secrets", [])

    for secret in secrets:
        secret_id = secret.get("id", "<unknown>")
        owner = secret.get("owner_service", "")
        if not owner:
            continue
        if owner not in known:
            report.add_violation(
                check,
                f"config/secret-catalog.json#/secrets[id={secret_id!r}]/owner_service",
                f"secret '{secret_id}' owner_service '{owner}' is not a node in the dependency graph — "
                "secret rotation scripts will target a phantom service",
            )


# ---------------------------------------------------------------------------
# Check 4: gate-bypass receipts → waiver catalog reason codes
# ---------------------------------------------------------------------------


def check_gate_bypass_reason_codes(report: IntegrityReport) -> None:
    """Every committed bypass receipt must reference a reason code that exists in the catalog."""
    check = "gate-bypass→waiver-catalog"
    report.mark_ran(check)

    if not GATE_BYPASS_WAIVER_CATALOG_PATH.exists():
        return
    if not GATE_BYPASS_RECEIPT_DIR.exists():
        return

    catalog = _load_json(GATE_BYPASS_WAIVER_CATALOG_PATH)
    known_codes: set[str] = set(catalog.get("reason_codes", {}).keys())

    for receipt_path in sorted(GATE_BYPASS_RECEIPT_DIR.glob("*.json")):
        try:
            receipt = _load_json(receipt_path)
        except (OSError, json.JSONDecodeError):
            continue  # malformed receipts are caught by gate_bypass_waivers.py --validate

        waiver = receipt.get("waiver")
        if not isinstance(waiver, dict):
            continue  # legacy receipt — no reason_code field

        reason_code = waiver.get("reason_code", "")
        if reason_code and reason_code not in known_codes:
            rel_path = receipt_path.relative_to(REPO_ROOT)
            report.add_violation(
                check,
                str(rel_path),
                f"receipt references unknown reason_code '{reason_code}' — "
                "the code was removed from the waiver catalog after this receipt was written; "
                "update the receipt or restore the catalog entry",
            )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def run_all_checks() -> IntegrityReport:
    report = IntegrityReport()
    check_health_probe_services(report)
    check_api_gateway_services(report)
    check_secret_owner_services(report)
    check_gate_bypass_reason_codes(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate referential integrity across platform catalogs.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args(argv)

    try:
        report = run_all_checks()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("cross-catalog integrity", exc)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "passed": report.passed,
                    "checks_run": report.checks_run,
                    "violation_count": len(report.violations),
                    "violations": [{"check": v.check, "path": v.path, "message": v.message} for v in report.violations],
                },
                indent=2,
            )
        )
        return 0 if report.passed else 1

    print(f"Cross-catalog integrity: {len(report.checks_run)} check(s) run")
    if report.passed:
        print("All cross-catalog references are consistent.")
        return 0

    print(f"\n{len(report.violations)} violation(s) found:\n")
    for v in report.violations:
        print(f"  ERROR  {v.check}")
        print(f"         path:    {v.path}")
        print(f"         detail:  {v.message}")
        print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
