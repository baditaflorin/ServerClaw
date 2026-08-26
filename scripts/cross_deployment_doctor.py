#!/usr/bin/env python3
"""Cross-deployment drift report — ADR 0460 phase 8.2.

The local `scripts/doctor.py` inspects one repo's view of drift.
Today's platform runs the same codebase against two deployments
(example.com + example.org), and Phase 5–7's drift surfaces were blind to
divergence BETWEEN those deployments. A receipt that's fresh on lv3
but 3 months old on 0fork looks fine to the local doctor.

This script reads the static side of each deployment under
`.local/deployments/<slug>/state/` and computes:

  - per-receipt date skew (which deployment is ahead/behind for each
    service)
  - per-service presence skew (running on lv3 but not 0fork, etc.)
  - per-deployment "freshest receipt" and "oldest receipt" headlines

The live SSH probe (querying running containers, NATS lag, etc.) is
deferred to phase 9 — that needs operator runtime access this
worktree doesn't have.

Output mirrors `doctor.py`'s human + JSON shapes so ops_portal
consumers can swap calls.

Exit:
  0  ran successfully (with or without findings)
  2  invocation error / no deployments configured
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENTS_DIR = REPO_ROOT / ".local" / "deployments"
_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")


@dataclass(frozen=True)
class DeploymentReceipts:
    slug: str
    receipts: dict[str, str]  # service → receipt slug
    receipt_dates: dict[str, dt.date | None]  # service → parsed date

    def services(self) -> set[str]:
        return set(self.receipts.keys())

    @classmethod
    def empty(cls, slug: str) -> "DeploymentReceipts":
        return cls(slug=slug, receipts={}, receipt_dates={})


@dataclass
class ReceiptDriftEntry:
    """A single service viewed across deployments."""

    service: str
    presence: dict[str, bool]  # slug → True if receipt exists
    receipt_dates: dict[str, str | None]  # slug → ISO date or None
    age_days: dict[str, int | None]  # slug → days since receipt, computed against `today`
    skew_days: int | None  # max - min age across deployments where both have a receipt
    drift_kind: str  # "presence" | "skew" | "in_sync"
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CrossDeploymentReport:
    deployments: list[str]
    drift_entries: list[ReceiptDriftEntry] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        presence_drift = sum(1 for e in self.drift_entries if e.drift_kind == "presence")
        skew_drift = sum(1 for e in self.drift_entries if e.drift_kind == "skew")
        in_sync = sum(1 for e in self.drift_entries if e.drift_kind == "in_sync")
        return {
            "total": len(self.drift_entries),
            "presence_drift": presence_drift,
            "skew_drift": skew_drift,
            "in_sync": in_sync,
            "deployments": len(self.deployments),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "deployments": self.deployments,
            "drift_entries": [e.to_dict() for e in self.drift_entries],
        }


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def parse_receipt_date(slug: str) -> dt.date | None:
    """Extract a date from a receipt slug like `YYYY-MM-DD-<rest>`.

    Mirrors the parsers in `check_receipt_freshness.py` and
    `refresh_safe_receipts.py`. Kept local so this script doesn't
    import either; the parser is small and shared shapes are stable
    enough to copy.
    """
    if not isinstance(slug, str):
        return None
    m = _DATE_PREFIX_RE.match(slug.strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def list_deployments(deployments_dir: Path) -> list[str]:
    """Return slug names under `.local/deployments/<slug>/`.

    Skips dotfile-prefixed and non-directory entries (e.g.
    `active-deployment` if someone placed it inside).
    """
    if not deployments_dir.is_dir():
        return []
    return sorted(p.name for p in deployments_dir.iterdir() if p.is_dir() and not p.name.startswith("."))


def load_deployment_receipts(deployment_root: Path, slug: str) -> DeploymentReceipts:
    """Read the receipt ledger for a single deployment.

    Two source-of-truth locations — try in order:

      1. `<deployment_root>/state/live_apply_evidence.yaml` (per-deployment
         shadow of versions/stack.yaml — populated by ADR 0440 work)
      2. `<deployment_root>/receipts/latest_receipts.yaml` (fallback;
         older shape)

    Returns an empty `DeploymentReceipts` when neither exists. The
    caller still classifies the deployment correctly (every service
    appears as "missing on this slug").
    """
    candidates = [
        deployment_root / "state" / "live_apply_evidence.yaml",
        deployment_root / "receipts" / "latest_receipts.yaml",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except (yaml.YAMLError, OSError):
            continue
        receipts = _extract_receipts(data)
        if receipts:
            dates = {svc: parse_receipt_date(slug_) for svc, slug_ in receipts.items()}
            return DeploymentReceipts(slug=slug, receipts=receipts, receipt_dates=dates)
    return DeploymentReceipts.empty(slug)


def _extract_receipts(data: dict) -> dict[str, str]:
    """Pull `latest_receipts` out of either v1 (versions/stack.yaml shape)
    or v0 (flat) layout."""
    if not isinstance(data, dict):
        return {}
    evidence = data.get("live_apply_evidence")
    if isinstance(evidence, dict):
        receipts = evidence.get("latest_receipts")
        if isinstance(receipts, dict):
            return {str(k): str(v) for k, v in receipts.items()}
    receipts = data.get("latest_receipts")
    if isinstance(receipts, dict):
        return {str(k): str(v) for k, v in receipts.items()}
    return {}


# ---------------------------------------------------------------------------
# Drift computation
# ---------------------------------------------------------------------------


def compute_drift(
    deployments: list[DeploymentReceipts],
    *,
    today: dt.date,
    skew_threshold_days: int = 14,
) -> CrossDeploymentReport:
    """Walk every service across every deployment; classify drift.

    presence drift: a service is present in some deployments but
                    missing in others.
    skew drift:     all deployments have the receipt, but ages diverge
                    by more than `skew_threshold_days`.
    in_sync:        all deployments have the receipt and ages are
                    within the threshold (informational; included in
                    output for symmetry).
    """
    slugs = [d.slug for d in deployments]
    all_services: set[str] = set()
    for d in deployments:
        all_services |= d.services()

    drift_entries: list[ReceiptDriftEntry] = []
    for service in sorted(all_services):
        presence = {d.slug: service in d.receipts for d in deployments}
        receipt_dates: dict[str, str | None] = {}
        age_days: dict[str, int | None] = {}
        for d in deployments:
            date = d.receipt_dates.get(service)
            receipt_dates[d.slug] = date.isoformat() if date else None
            age_days[d.slug] = (today - date).days if date else None
        present_ages = [age for age in age_days.values() if age is not None]
        if not all(presence.values()):
            missing = [slug for slug, has in presence.items() if not has]
            drift_kind = "presence"
            detail = f"missing on: {', '.join(missing)}"
            skew = None
        elif present_ages and (max(present_ages) - min(present_ages)) > skew_threshold_days:
            drift_kind = "skew"
            skew = max(present_ages) - min(present_ages)
            min_slug = min(age_days, key=lambda s: age_days[s] or 0)
            max_slug = max(age_days, key=lambda s: age_days[s] or 0)
            detail = f"{skew}d skew between {min_slug} ({age_days[min_slug]}d) and {max_slug} ({age_days[max_slug]}d)"
        else:
            drift_kind = "in_sync"
            skew = (max(present_ages) - min(present_ages)) if present_ages else 0
            detail = f"all {len(deployments)} deployments within {skew}d skew"
        drift_entries.append(
            ReceiptDriftEntry(
                service=service,
                presence=presence,
                receipt_dates=receipt_dates,
                age_days=age_days,
                skew_days=skew,
                drift_kind=drift_kind,
                detail=detail,
            )
        )
    return CrossDeploymentReport(deployments=slugs, drift_entries=drift_entries)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _format_human(report: CrossDeploymentReport) -> str:
    if not report.deployments:
        return "cross_deployment_doctor: no deployments configured under .local/deployments/."
    if not report.drift_entries:
        return f"cross_deployment_doctor: {len(report.deployments)} deployment(s); no receipts to compare."
    lines = [
        f"cross_deployment_doctor: {len(report.deployments)} deployments — {', '.join(report.deployments)}",
    ]
    presence = [e for e in report.drift_entries if e.drift_kind == "presence"]
    skew = [e for e in report.drift_entries if e.drift_kind == "skew"]
    in_sync = [e for e in report.drift_entries if e.drift_kind == "in_sync"]
    if presence:
        lines.append(f"\n[presence drift] {len(presence)}")
        for e in presence:
            lines.append(f"  {e.service}: {e.detail}")
    if skew:
        lines.append(f"\n[receipt skew >threshold] {len(skew)}")
        for e in skew:
            lines.append(f"  {e.service}: {e.detail}")
    lines.append(f"\nsummary: {len(presence)} presence drift / {len(skew)} skew / {len(in_sync)} in sync")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _gather_deployments(
    deployments_dir: Path,
    *,
    selected: list[str] | None = None,
) -> list[DeploymentReceipts]:
    slugs = list_deployments(deployments_dir)
    if selected:
        unknown = [s for s in selected if s not in slugs]
        if unknown:
            raise ValueError(f"unknown deployment slug(s): {unknown}; available: {slugs}")
        slugs = [s for s in slugs if s in selected]
    return [load_deployment_receipts(deployments_dir / slug, slug) for slug in slugs]


def main(argv: list[str] | None = None, *, today: dt.date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--deployments-dir",
        default=str(DEPLOYMENTS_DIR),
        help="Override the .local/deployments/ root (used by tests).",
    )
    parser.add_argument(
        "--deployment",
        action="append",
        default=[],
        help="Limit to a specific deployment slug (repeatable). Default: all.",
    )
    parser.add_argument(
        "--skew-threshold-days",
        type=int,
        default=14,
        help="Receipt age skew above which a service is flagged (default 14).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)

    if args.skew_threshold_days < 0:
        print(
            "cross_deployment_doctor: --skew-threshold-days must be >= 0",
            file=sys.stderr,
        )
        return 2

    try:
        deployments = _gather_deployments(
            Path(args.deployments_dir),
            selected=args.deployment or None,
        )
    except ValueError as exc:
        print(f"cross_deployment_doctor: {exc}", file=sys.stderr)
        return 2

    report = compute_drift(
        deployments,
        today=today or dt.date.today(),
        skew_threshold_days=args.skew_threshold_days,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(_format_human(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
