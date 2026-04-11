#!/usr/bin/env python3
"""Generate Prometheus SLO config files from config/slo-catalog.json.

Generates:
  - config/prometheus/rules/slo_alerts.yml
  - config/prometheus/rules/slo_rules.yml
  - config/prometheus/file_sd/slo_targets.yml

Each service block is wrapped in:
  # BEGIN SERVICE: <service_id>
  # END SERVICE: <service_id>
markers so that decommission_service.py can surgically remove them.

Usage:
    python3 scripts/generate_slo_config.py --dry-run
    python3 scripts/generate_slo_config.py --write
    python3 scripts/generate_slo_config.py --check    # exits 1 if files would change (CI)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

SLO_CATALOG_PATH = REPO_ROOT / "config" / "slo-catalog.json"
SLO_ALERTS_PATH = REPO_ROOT / "config" / "prometheus" / "rules" / "slo_alerts.yml"
SLO_RULES_PATH = REPO_ROOT / "config" / "prometheus" / "rules" / "slo_rules.yml"
SLO_TARGETS_PATH = REPO_ROOT / "config" / "prometheus" / "file_sd" / "slo_targets.yml"

GENERATED_HEADER = (
    "# AUTO-GENERATED from config/slo-catalog.json — do not edit manually\n"
    "# Regenerate: python3 scripts/generate_slo_config.py --write\n"
)


# ============================================================================
# Catalog loading
# ============================================================================


def load_slo_catalog() -> dict[str, Any]:
    if not SLO_CATALOG_PATH.is_file():
        raise FileNotFoundError(f"SLO catalog not found: {SLO_CATALOG_PATH}")
    with SLO_CATALOG_PATH.open() as fh:
        return json.load(fh)


# ============================================================================
# Helpers
# ============================================================================


def metric_slug(slo_id: str) -> str:
    """Convert slo-id to prometheus metric name component (hyphens → underscores)."""
    return slo_id.replace("-", "_")


def error_budget(objective_percent: float) -> float:
    return (100.0 - objective_percent) / 100.0


# ============================================================================
# Alerts generation
# ============================================================================


def _alerts_block(slo: dict[str, Any]) -> str:
    """Return the YAML text for one SLO's alert rules (fast-burn + slow-burn)."""
    slo_id = slo["id"]
    slug = metric_slug(slo_id)
    service_id = slo["service_id"]
    indicator = slo["indicator"]
    desc = slo.get("description", "")
    budget = error_budget(slo["objective_percent"])
    budget_str = f"{budget:.6f}"

    lines: list[str] = []
    lines.append(f"# BEGIN SERVICE: {service_id}")

    # --- Fast burn (14x, 2m window) ---
    lines.append(f"      - alert: SLOFastBurn_{slug}")
    lines.append(
        f"        expr: (slo:{slug}:error_rate_5m > (14 * {budget_str})) and"
        f" (slo:{slug}:error_rate_1h > (14 * {budget_str}))"
    )
    lines.append("        for: 2m")
    lines.append("        labels:")
    lines.append("          severity: critical")
    lines.append(f"          service_id: {service_id}")
    lines.append(f"          slo_id: {slo_id}")
    lines.append(f"          indicator: {indicator}")
    lines.append("        annotations:")
    lines.append(f"          summary: {slo_id} is burning its error budget at 14x")
    lines.append(f"          description: {desc}")
    lines.append("          runbook: docs/runbooks/slo-tracking.md")

    # --- Slow burn (6x, 15m window) ---
    lines.append(f"      - alert: SLOSlowBurn_{slug}")
    lines.append(
        f"        expr: (slo:{slug}:error_rate_6h > (6 * {budget_str})) and"
        f" (slo:{slug}:error_rate_30d > (6 * {budget_str}))"
    )
    lines.append("        for: 15m")
    lines.append("        labels:")
    lines.append("          severity: warning")
    lines.append(f"          service_id: {service_id}")
    lines.append(f"          slo_id: {slo_id}")
    lines.append(f"          indicator: {indicator}")
    lines.append("        annotations:")
    lines.append(f"          summary: {slo_id} is burning its error budget at 6x")
    lines.append(f"          description: {desc}")
    lines.append("          runbook: docs/runbooks/slo-tracking.md")

    lines.append(f"# END SERVICE: {service_id}")
    return "\n".join(lines)


def build_slo_alerts(catalog: dict[str, Any]) -> str:
    parts: list[str] = [
        GENERATED_HEADER,
        "groups:",
        "  - name: slo_alert_rules",
        "    interval: 1m",
        "    rules:",
    ]
    for slo in catalog["slos"]:
        parts.append(_alerts_block(slo))
    return "\n".join(parts) + "\n"


# ============================================================================
# Recording rules generation
# ============================================================================


def _rules_block(slo: dict[str, Any]) -> str:
    """Return the YAML text for one SLO's recording rules."""
    slo_id = slo["id"]
    slug = metric_slug(slo_id)
    service_id = slo["service_id"]
    indicator = slo["indicator"]
    budget = error_budget(slo["objective_percent"])
    budget_str = f"{budget:.6f}"

    job_selector = f'job="slo-blackbox",slo_id="{slo_id}"'

    lines: list[str] = []
    lines.append(f"# BEGIN SERVICE: {service_id}")

    # Success ratio rules — 4 windows
    for window in ("5m", "1h", "6h", "30d"):
        lines.append(f"      - record: slo:{slug}:success_ratio_{window}")
        lines.append(f"        expr: avg_over_time(probe_success{{{job_selector}}}[{window}])")
        lines.append("        labels:")
        lines.append(f"          slo_id: {slo_id}")
        lines.append(f"          service_id: {service_id}")
        lines.append(f"          indicator: {indicator}")

    # Error rate rules — 4 windows
    for window in ("5m", "1h", "6h", "30d"):
        lines.append(f"      - record: slo:{slug}:error_rate_{window}")
        lines.append(f"        expr: 1 - slo:{slug}:success_ratio_{window}")
        lines.append("        labels:")
        lines.append(f"          slo_id: {slo_id}")
        lines.append(f"          service_id: {service_id}")
        lines.append(f"          indicator: {indicator}")

    lines.append(f"# END SERVICE: {service_id}")
    return "\n".join(lines)


def build_slo_rules(catalog: dict[str, Any]) -> str:
    parts: list[str] = [
        GENERATED_HEADER,
        "groups:",
        "  - name: slo_recording_rules",
        "    interval: 5m",
        "    rules:",
    ]
    for slo in catalog["slos"]:
        parts.append(_rules_block(slo))
    return "\n".join(parts) + "\n"


# ============================================================================
# File-SD targets generation
# ============================================================================


def _target_block(slo: dict[str, Any]) -> str:
    """Return the YAML text for one SLO's file-SD target entry."""
    slo_id = slo["id"]
    service_id = slo["service_id"]
    indicator = slo["indicator"]
    target_url = slo["target_url"]
    probe_mod = slo["probe_module"]

    lines: list[str] = []
    lines.append(f"# BEGIN SERVICE: {service_id}")
    lines.append("- targets:")
    lines.append(f"    - {target_url}")
    lines.append("  labels:")
    lines.append(f"    service_id: {service_id}")
    lines.append(f"    slo_id: {slo_id}")
    lines.append(f"    indicator: {indicator}")
    lines.append(f"    probe_module: {probe_mod}")
    lines.append(f"# END SERVICE: {service_id}")
    return "\n".join(lines)


def build_slo_targets(catalog: dict[str, Any]) -> str:
    parts: list[str] = [GENERATED_HEADER]
    for slo in catalog["slos"]:
        parts.append(_target_block(slo))
    return "\n".join(parts) + "\n"


# ============================================================================
# Write / check helpers
# ============================================================================


def _read_existing(path: Path) -> str:
    if path.is_file():
        return path.read_text()
    return ""


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ============================================================================
# Main
# ============================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Prometheus SLO config files from config/slo-catalog.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Write generated files to disk.")
    mode.add_argument("--check", action="store_true", help="Exit non-zero if files would change (CI mode).")
    mode.add_argument("--dry-run", action="store_true", help="Print what would be written; do not write.")

    args = parser.parse_args(argv)

    try:
        catalog = load_slo_catalog()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    outputs = {
        SLO_ALERTS_PATH: build_slo_alerts(catalog),
        SLO_RULES_PATH: build_slo_rules(catalog),
        SLO_TARGETS_PATH: build_slo_targets(catalog),
    }

    changed: list[str] = []
    for path, content in outputs.items():
        if _read_existing(path) != content:
            changed.append(str(path.relative_to(REPO_ROOT)))

    if args.dry_run:
        for path, content in outputs.items():
            rel = str(path.relative_to(REPO_ROOT))
            status = "CHANGED" if rel in changed else "unchanged"
            print(f"--- {rel}  [{status}] ---")
            print(content[:800])
            if len(content) > 800:
                print(f"  ... ({len(content)} bytes total)")
            print()
        return 0

    if args.check:
        if changed:
            print(f"Would change: {changed}", file=sys.stderr)
            return 1
        return 0

    if args.write:
        for path, content in outputs.items():
            _write_file(path, content)
            rel = str(path.relative_to(REPO_ROOT))
            print(f"Wrote {rel}")
        return 0

    # Default: print summary
    print(
        json.dumps(
            {
                "slo_count": len(catalog["slos"]),
                "outputs": [str(p.relative_to(REPO_ROOT)) for p in outputs],
                "would_change": changed,
                "hint": "Pass --write to write files, --dry-run to preview, --check for CI.",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
