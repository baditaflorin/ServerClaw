#!/usr/bin/env python3
"""`make doctor` — single-command drift report — ADR 0450 phase 5.1.

Aggregates every Phase-1/2/3/4 drift signal that the platform currently
surfaces. Returns a single human-readable summary or a structured JSON
view, plus pointers to the heal-X / explain-X companions when they
exist.

Signals included (each is best-effort; a missing or broken sub-tool is
reported as "unavailable" rather than failing the whole run):

  - stale_receipts        — `scripts/check_receipt_freshness.py --json`
  - dangling_surfaces     — `scripts/generate_traceability.py --validate`
  - validator_gaps        — `scripts/generate_validator_catalogue.py --print`
  - late_bound_defaults   — `scripts/validate_no_hardcoded_topology.py --rule late_bound_default --json`
  - safe_to_refresh       — `scripts/refresh_safe_receipts.py --json`
  - unreserved_adrs       — disk vs reservations.yaml diff
  - blocked_substrate     — `.gitkeep` files referenced by workstream surfaces

Default output is human-readable, colored by severity. `--json` emits
the same data as a structured payload for ops_portal consumption.
`--quiet` prints only the summary line. `--strict` exits 1 if any
signal is non-zero (advisory by default).

The aggregator does NOT call any sub-tool that requires network or
SSH — only the local file scanners. Production-only signals (live
alerts, runtime probes) belong in the Windmill schedule, not here.

Exit codes:
    0  doctor ran (with or without findings, advisory)
    1  --strict and at least one signal non-zero
    2  invocation error
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Signal:
    """One row in the doctor report."""

    name: str
    headline: str  # one-line summary
    count: int  # numeric severity, 0 = clean
    detail: dict[str, Any] = field(default_factory=dict)
    heal_command: str | None = None  # `make heal-X` or equivalent
    explain_command: str | None = None  # `make explain-X` or equivalent
    error: str | None = None  # set when the sub-tool failed entirely

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Signal probes
# ---------------------------------------------------------------------------


def _run_python_script(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a python script via uv if available, else direct."""
    if shutil.which("uv"):
        cmd = ["uv", "run", "--with", "pyyaml", "python", *args]
    else:
        cmd = ["python3", *args]
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)


def probe_stale_receipts(repo_root: Path) -> Signal:
    """Run check_receipt_freshness.py --json and parse stale count."""
    script = repo_root / "scripts" / "check_receipt_freshness.py"
    if not script.is_file():
        return Signal(
            name="stale_receipts",
            headline="check_receipt_freshness.py not found",
            count=0,
            error="script missing",
        )
    proc = _run_python_script([str(script), "--json"], cwd=repo_root)
    if proc.returncode == 2:
        return Signal(
            name="stale_receipts",
            headline=f"check_receipt_freshness errored: {proc.stderr.strip()[:80]}",
            count=0,
            error=proc.stderr.strip(),
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return Signal(
            name="stale_receipts",
            headline="check_receipt_freshness emitted unparseable JSON",
            count=0,
            error=proc.stdout[:200],
        )
    summary = payload.get("summary", {})
    stale = int(summary.get("stale", 0))
    total = int(summary.get("total", 0))
    window = int(summary.get("max_age_days", 30))
    return Signal(
        name="stale_receipts",
        headline=f"{stale}/{total} stale at {window}d window",
        count=stale,
        detail=summary,
        heal_command="python3 scripts/refresh_safe_receipts.py --apply",
        explain_command="python3 scripts/check_receipt_freshness.py",
    )


def probe_dangling_surfaces(repo_root: Path) -> Signal:
    """Run generate_traceability.py --validate; parse exit code + summary."""
    script = repo_root / "scripts" / "generate_traceability.py"
    if not script.is_file():
        return Signal(
            name="dangling_surfaces",
            headline="generate_traceability.py not found",
            count=0,
            error="script missing",
        )
    # --validate exits 1 on dangling refs. We need both exit code AND
    # parsed counts; read traceability.yaml for the structured count.
    traceability = repo_root / "build" / "traceability.yaml"
    proc = _run_python_script([str(script), "--validate"], cwd=repo_root)
    count = 0
    detail: dict[str, Any] = {}
    if traceability.is_file():
        try:
            import yaml

            data = yaml.safe_load(traceability.read_text()) or {}
            summary = data.get("summary", {}) or {}
            count = int(summary.get("with_dangling_surfaces", 0))
            detail = summary
        except Exception:
            pass
    if proc.returncode == 0 and count == 0:
        headline = "no dangling shared_surfaces"
    else:
        headline = f"{count} workstream(s) with dangling shared_surfaces"
    return Signal(
        name="dangling_surfaces",
        headline=headline,
        count=count,
        detail=detail,
        heal_command="bash .githooks/post-merge  # auto-fix recent renames",
        explain_command="python3 scripts/generate_traceability.py --validate",
    )


def probe_validator_gaps(repo_root: Path) -> Signal:
    """Read build/validator-catalogue.yaml summary if present."""
    catalogue = repo_root / "build" / "validator-catalogue.yaml"
    if not catalogue.is_file():
        return Signal(
            name="validator_gaps",
            headline="validator-catalogue.yaml not generated",
            count=0,
            heal_command="python3 scripts/generate_validator_catalogue.py --write",
        )
    try:
        import yaml

        data = yaml.safe_load(catalogue.read_text()) or {}
    except Exception as exc:
        return Signal(
            name="validator_gaps",
            headline=f"validator-catalogue.yaml unparseable: {exc}",
            count=0,
            error=str(exc),
        )
    summary = data.get("summary", {}) or {}
    no_doc = int(summary.get("without_docstring", 0))
    no_adr = int(summary.get("without_related_adr", 0))
    total = int(summary.get("total", 0))
    # We surface the docstring gap as the primary signal (LLM ergonomics);
    # the ADR-ref gap is informational.
    headline = f"{total} validators catalogued; {no_doc} missing docstring, {no_adr} lack ADR ref"
    return Signal(
        name="validator_gaps",
        headline=headline,
        count=no_doc,
        detail={"without_docstring": no_doc, "without_related_adr": no_adr, "total": total},
        explain_command="cat build/validator-catalogue.yaml",
    )


def probe_late_bound_defaults(repo_root: Path) -> Signal:
    """Run validate_no_hardcoded_topology.py --rule late_bound_default --json."""
    script = repo_root / "scripts" / "validate_no_hardcoded_topology.py"
    if not script.is_file():
        return Signal(
            name="late_bound_defaults",
            headline="validate_no_hardcoded_topology.py not found",
            count=0,
            error="script missing",
        )
    proc = _run_python_script([str(script), "--rule", "late_bound_default", "--json"], cwd=repo_root)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return Signal(
            name="late_bound_defaults",
            headline="topology validator emitted unparseable JSON",
            count=0,
            error=proc.stdout[:200],
        )
    count = int(payload.get("finding_count", 0))
    headline = (
        "no late-bound defaults in role defaults"
        if count == 0
        else f"{count} late-bound default('<known-prod-IP>') in role defaults"
    )
    return Signal(
        name="late_bound_defaults",
        headline=headline,
        count=count,
        explain_command="python3 scripts/validate_no_hardcoded_topology.py --rule late_bound_default",
    )


def probe_safe_to_refresh(repo_root: Path) -> Signal:
    """Run refresh_safe_receipts.py --json; surface the safe count."""
    script = repo_root / "scripts" / "refresh_safe_receipts.py"
    if not script.is_file():
        return Signal(
            name="safe_to_refresh",
            headline="refresh_safe_receipts.py not found",
            count=0,
            error="script missing",
        )
    proc = _run_python_script([str(script), "--json"], cwd=repo_root)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return Signal(
            name="safe_to_refresh",
            headline="refresh_safe_receipts emitted unparseable JSON",
            count=0,
            error=proc.stdout[:200],
        )
    summary = payload.get("summary", {})
    safe = int(summary.get("safe_to_refresh", 0))
    needs = int(summary.get("needs_review", 0))
    headline = f"{safe} receipts safe to refresh, {needs} need converge re-run"
    return Signal(
        name="safe_to_refresh",
        headline=headline,
        count=safe,
        detail=summary,
        heal_command="python3 scripts/refresh_safe_receipts.py --apply",
        explain_command="python3 scripts/refresh_safe_receipts.py",
    )


def probe_unreserved_adrs(repo_root: Path) -> Signal:
    """Compare disk ADRs against reservations.yaml.

    Today this is informational only — we only flag ADRs on disk whose
    number is NOT in reservations.yaml. The reservation system is
    optional, so the count surfaces "ADRs that bypassed the reservation
    flow" rather than "errors".
    """
    adr_dir = repo_root / "docs" / "adr"
    if not adr_dir.is_dir():
        return Signal(
            name="unreserved_adrs",
            headline="docs/adr/ not found",
            count=0,
            error="directory missing",
        )
    on_disk: set[int] = set()
    import re

    rx = re.compile(r"^(\d{4})-")
    for path in adr_dir.iterdir():
        if not path.is_file() or path.suffix != ".md":
            continue
        m = rx.match(path.name)
        if m:
            on_disk.add(int(m.group(1)))
    res_path = adr_dir / "index" / "reservations.yaml"
    reserved: set[int] = set()
    if res_path.is_file():
        try:
            import yaml

            data = yaml.safe_load(res_path.read_text()) or {}
            for entry in data.get("reservations") or []:
                if not isinstance(entry, dict):
                    continue
                try:
                    start = int(entry.get("start"))
                    end = int(entry.get("end", entry.get("start")))
                except (TypeError, ValueError):
                    continue
                for n in range(start, end + 1):
                    reserved.add(n)
        except Exception:
            pass
    unreserved = sorted(on_disk - reserved)
    # Today nearly every ADR is unreserved (the reservation flow was
    # only added in ws-0449). We surface this as informational, count=0.
    return Signal(
        name="unreserved_adrs",
        headline=f"{len(unreserved)} ADR(s) on disk without an explicit reservation (informational)",
        count=0,  # not a drift signal yet — would become one after a cleanup pass
        detail={"sample": [f"{n:04d}" for n in unreserved[:5]]},
        explain_command="cat docs/adr/index/reservations.yaml",
    )


def probe_blocked_substrate(repo_root: Path) -> Signal:
    """Find `.gitkeep` files under collections/ansible_collections/lv3/platform/."""
    base = repo_root / "collections" / "ansible_collections" / "lv3" / "platform"
    if not base.is_dir():
        return Signal(
            name="blocked_substrate",
            headline="collections base path not present",
            count=0,
        )
    blockers: list[str] = []
    for path in base.rglob(".gitkeep"):
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)
        blockers.append(rel)
    blockers.sort()
    return Signal(
        name="blocked_substrate",
        headline=f"{len(blockers)} .gitkeep placeholder(s) in collection substrate",
        count=len(blockers),
        detail={"paths": blockers[:5]},
        explain_command=("find collections/ansible_collections/lv3/platform -name .gitkeep"),
    )


def probe_promotion_eligible(repo_root: Path) -> Signal:
    """ADR 0460 phase 8.1 — surface gates eligible for advisory→required
    promotion. Reads `receipts/gate-runs/` via promotion_tracker.py and
    counts the eligible bucket. Informational: count is the number of
    gates ready to promote, not a drift indicator. The point is to
    nudge an operator to flip them, not to block a push.
    """
    script = repo_root / "scripts" / "promotion_tracker.py"
    if not script.is_file():
        return Signal(
            name="promotion_eligible",
            headline="promotion_tracker.py not found",
            count=0,
            error="script missing",
        )
    proc = _run_python_script([str(script), "--json"], cwd=repo_root)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return Signal(
            name="promotion_eligible",
            headline="promotion_tracker emitted unparseable JSON",
            count=0,
            error=proc.stdout[:200],
        )
    summary = payload.get("summary", {}).get("by_status", {})
    eligible = int(summary.get("eligible", 0))
    streaking = int(summary.get("streaking", 0))
    headline = f"{eligible} gate(s) eligible for advisory→required promotion ({streaking} streaking)"
    return Signal(
        name="promotion_eligible",
        headline=headline,
        # Informational: never count > 0 from a drift perspective.
        # The eligible bucket is opportunity, not failure.
        count=0,
        detail=summary,
        explain_command="python3 scripts/promotion_tracker.py",
    )


def probe_cross_deployment_drift(repo_root: Path) -> Signal:
    """ADR 0460 phase 8.2 — read .local/deployments/<slug>/state/ and
    surface receipt drift between deployments. Worktrees that don't
    carry .local/ (per CLAUDE.md) get count=0 with a "no deployments"
    note — same graceful degradation pattern other probes use.
    """
    script = repo_root / "scripts" / "cross_deployment_doctor.py"
    if not script.is_file():
        return Signal(
            name="cross_deployment_drift",
            headline="cross_deployment_doctor.py not found",
            count=0,
            error="script missing",
        )
    proc = _run_python_script([str(script), "--json"], cwd=repo_root)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return Signal(
            name="cross_deployment_drift",
            headline="cross_deployment_doctor emitted unparseable JSON",
            count=0,
            error=proc.stdout[:200],
        )
    summary = payload.get("summary", {})
    presence = int(summary.get("presence_drift", 0))
    skew = int(summary.get("skew_drift", 0))
    deployments = int(summary.get("deployments", 0))
    if deployments == 0:
        return Signal(
            name="cross_deployment_drift",
            headline="no deployments configured under .local/deployments/",
            count=0,
        )
    drift_count = presence + skew
    return Signal(
        name="cross_deployment_drift",
        headline=(
            f"{drift_count} cross-deployment drift entries "
            f"({presence} presence, {skew} skew) across {deployments} deployment(s)"
        ),
        count=drift_count,
        detail=summary,
        explain_command="python3 scripts/cross_deployment_doctor.py",
    )


PROBES = (
    probe_stale_receipts,
    probe_safe_to_refresh,
    probe_dangling_surfaces,
    probe_validator_gaps,
    probe_late_bound_defaults,
    probe_unreserved_adrs,
    probe_blocked_substrate,
    probe_promotion_eligible,
    probe_cross_deployment_drift,
)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_all(repo_root: Path) -> list[Signal]:
    return [probe(repo_root) for probe in PROBES]


def format_human(signals: list[Signal]) -> str:
    lines: list[str] = []
    for s in signals:
        marker = "[ok]   " if s.count == 0 and not s.error else f"[!]    "
        if s.error:
            marker = "[err]  "
        lines.append(f"  {marker}{s.name:<22} {s.headline}")
        if s.heal_command and s.count > 0:
            lines.append(f"           heal:    {s.heal_command}")
        if s.explain_command and (s.count > 0 or s.error):
            lines.append(f"           explain: {s.explain_command}")
    nonzero = sum(1 for s in signals if s.count > 0)
    erred = sum(1 for s in signals if s.error)
    lines.append("")
    lines.append(f"summary: {nonzero}/{len(signals)} signal(s) non-zero, {erred} errored")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repo root override (default: this script's repo)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable")
    parser.add_argument("--quiet", action="store_true", help="Print only the summary line")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any signal is non-zero (default: advisory, exit 0)",
    )
    parser.add_argument(
        "--probes",
        default=os.environ.get("DOCTOR_PROBES", ""),
        help="Comma-separated probe names to run (default: all). Useful for tests.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root)
    probes = list(PROBES)
    if args.probes:
        wanted = {p.strip() for p in args.probes.split(",") if p.strip()}
        probes = [p for p in probes if p.__name__.removeprefix("probe_") in wanted]
        if not probes:
            print(f"doctor: no probes matched {sorted(wanted)}", file=sys.stderr)
            return 2

    signals = [probe(repo_root) for probe in probes]

    if args.json:
        print(
            json.dumps(
                {
                    "summary": {
                        "total": len(signals),
                        "nonzero": sum(1 for s in signals if s.count > 0),
                        "errored": sum(1 for s in signals if s.error),
                    },
                    "signals": [s.to_dict() for s in signals],
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif args.quiet:
        nonzero = sum(1 for s in signals if s.count > 0)
        print(f"doctor: {nonzero}/{len(signals)} signal(s) non-zero")
    else:
        print(format_human(signals))

    if args.strict and any(s.count > 0 for s in signals):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
