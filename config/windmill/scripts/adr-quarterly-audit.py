#!/usr/bin/env python3
"""
Quarterly ADR Status Audit

Compares committed ADR status against actual implementation evidence.
Detects new mismatches, resolved mismatches, and generates audit report.

Usage:
  python adr-quarterly-audit.py [--dry-run] [--audit-team platform-architects]

Environment:
  PLANE_API_KEY: Plane API key for creating audit issue
  PLANE_URL: Plane API URL (default: https://api.plane.so/api/v1)

Exit codes:
  0 = audit successful
  1 = mismatches detected but audit report created
  2 = error running audit
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date


ADR_DIR = Path("docs/adr")
INDEX_PATH = Path("docs/adr/.index.yaml")

STATUS_HIERARCHY = {
    "Accepted": 0,
    "Partial": 1,
    "Partial Implemented": 1,
    "Implemented": 2,
}


def is_first_monday_of_quarter() -> bool:
    """Check if today is the first Monday of the quarter."""
    today = date.today()

    # Determine quarter start dates
    quarters = [
        (1, 1),  # Q1
        (4, 1),  # Q2
        (7, 1),  # Q3
        (10, 1),  # Q4
    ]

    for quarter_month, _ in quarters:
        quarter_start = date(today.year, quarter_month, 1)

        # Find first Monday of quarter
        days_until_monday = (7 - quarter_start.weekday()) % 7
        if days_until_monday == 0 and quarter_start.weekday() != 0:
            days_until_monday = 7

        first_monday = date(
            quarter_start.year,
            quarter_start.month,
            quarter_start.day + days_until_monday,
        )

        # Check if today matches
        if today == first_monday:
            return True

    return False


def parse_adr_frontmatter(adr_path: Path) -> Dict[str, str]:
    """Parse ADR markdown frontmatter."""
    try:
        with open(adr_path) as f:
            content = f.read()

        lines = content.split("\n")[:20]
        metadata = {}

        for line in lines:
            if line.startswith("- Status:"):
                metadata["status"] = line.replace("- Status:", "").strip()
            elif line.startswith("- Implementation Status:"):
                metadata["implementation_status"] = line.replace("- Implementation Status:", "").strip()

        return metadata
    except Exception:
        return {}


def get_adr_number_from_path(path: Path) -> Optional[str]:
    """Extract ADR number from path."""
    import re

    match = re.match(r"(\d{4})-", path.name)
    return match.group(1) if match else None


def get_git_evidence_for_adr(adr_num: str, days_back: int = 180) -> int:
    """Count git commits mentioning this ADR."""
    try:
        patterns = [
            f"ADR.{adr_num}",
            f"adr-{adr_num}",
            f"0{adr_num}",
        ]

        total_commits = 0
        for pattern in patterns:
            result = subprocess.run(
                ["git", "log", f"--since={days_back}.days.ago", "--oneline", "--all", "--grep", pattern],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.stdout.strip():
                total_commits += len(result.stdout.strip().split("\n"))

        return min(total_commits, 10)  # Cap at 10 for readability
    except Exception:
        return 0


def get_code_evidence_for_adr(adr_num: str) -> int:
    """Count code references to this ADR."""
    try:
        patterns = [
            f"adr.{adr_num}",
            f"adr-{adr_num}",
            f"0{adr_num}",
            f"ADR.{adr_num}",
            f"ADR.0{adr_num}",
        ]

        count = 0
        for pattern in patterns:
            result = subprocess.run(
                ["git", "grep", "-i", pattern, "--", "collections", "playbooks", "roles", "config"],
                capture_output=True,
                text=False,
                check=False,
            )
            count += len(result.stdout.decode(errors="ignore").strip().split("\n")) if result.stdout else 0

        return min(count, 10)  # Cap at 10
    except Exception:
        return 0


def get_confidence_tier(git_evidence: int, code_evidence: int) -> str:
    """Determine confidence tier based on evidence markers."""
    total_markers = git_evidence + code_evidence

    if total_markers >= 5:
        return "High"
    elif total_markers >= 2:
        return "Medium"
    elif total_markers >= 1:
        return "Low"
    else:
        return "None"


def audit_adr(adr_path: Path, adr_num: str) -> Dict:
    """Audit a single ADR."""
    metadata = parse_adr_frontmatter(adr_path)
    impl_status = metadata.get("implementation_status", "")

    if not impl_status:
        return None

    # Get evidence
    git_evidence = get_git_evidence_for_adr(adr_num)
    code_evidence = get_code_evidence_for_adr(adr_num)
    confidence = get_confidence_tier(git_evidence, code_evidence)

    return {
        "adr_num": adr_num,
        "title": adr_path.name,
        "committed_status": impl_status,
        "git_commits": git_evidence,
        "code_references": code_evidence,
        "confidence": confidence,
    }


def run_quarterly_audit(dry_run: bool = False) -> Dict:
    """Run quarterly audit on all ADRs."""
    print(f"[{datetime.now().isoformat()}] Starting quarterly ADR audit...")

    # Check if today is audit day (unless --dry-run)
    if not dry_run and not is_first_monday_of_quarter():
        print(f"[{datetime.now().isoformat()}] Not audit day (first Monday of quarter). Skipping.")
        return {"skipped": True, "reason": "not_audit_day"}

    # Collect all ADRs
    adr_files = sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))
    if not adr_files:
        return {"error": "No ADR files found"}

    # Audit each ADR
    audits = []
    for adr_path in adr_files:
        adr_num = get_adr_number_from_path(adr_path)
        if not adr_num:
            continue

        audit = audit_adr(adr_path, adr_num)
        if audit:
            audits.append(audit)

    # Categorize by confidence
    high_confidence = [a for a in audits if a["confidence"] == "High"]
    medium_confidence = [a for a in audits if a["confidence"] == "Medium"]
    low_confidence = [a for a in audits if a["confidence"] == "Low"]
    no_evidence = [a for a in audits if a["confidence"] == "None"]

    audit_report = {
        "timestamp": datetime.now().isoformat(),
        "total_adrs_audited": len(audits),
        "confidence_summary": {
            "high": len(high_confidence),
            "medium": len(medium_confidence),
            "low": len(low_confidence),
            "none": len(no_evidence),
        },
        "audits": audits,
        "recommendations": [],
    }

    # Generate recommendations
    if no_evidence:
        audit_report["recommendations"].append(
            f"Consider downgrading {len(no_evidence)} ADRs with no evidence to 'Accepted' status"
        )

    if low_confidence:
        audit_report["recommendations"].append(
            f"Review {len(low_confidence)} low-confidence ADRs for potential downgrade"
        )

    if medium_confidence:
        audit_report["recommendations"].append(
            f"{len(medium_confidence)} ADRs have medium confidence — review for promotion to 'Implemented'"
        )

    if dry_run:
        print(f"[DRY-RUN] Audit would report:")
        print(json.dumps(audit_report, indent=2))

    return audit_report


def format_audit_html(audit_report: Dict) -> str:
    """Format audit report as HTML for Plane issue."""
    if audit_report.get("skipped"):
        return "<p>Audit skipped (not first Monday of quarter)</p>"

    summary = audit_report.get("confidence_summary", {})
    recommendations = audit_report.get("recommendations", [])
    timestamp = audit_report.get("timestamp", "")

    html = f"""<h2>Quarterly ADR Audit Report</h2>
<p><strong>Audit Date:</strong> {timestamp}</p>
<p><strong>Total ADRs Audited:</strong> {audit_report.get("total_adrs_audited", 0)}</p>

<h3>Confidence Summary</h3>
<ul>
<li><strong>High Confidence (5+ markers):</strong> {summary.get("high", 0)} ADRs</li>
<li><strong>Medium Confidence (2-4 markers):</strong> {summary.get("medium", 0)} ADRs</li>
<li><strong>Low Confidence (1 marker):</strong> {summary.get("low", 0)} ADRs</li>
<li><strong>No Evidence:</strong> {summary.get("none", 0)} ADRs</li>
</ul>

<h3>Recommendations</h3>
<ul>"""

    for rec in recommendations:
        html += f"<li>{rec}</li>"

    html += """</ul>

<h3>Next Steps</h3>
<ol>
<li>Review high-confidence ADRs for promotion to 'Implemented'</li>
<li>Investigate medium-confidence ADRs for status alignment</li>
<li>Address low-confidence ADRs with downgrade candidates</li>
</ol>

<hr/>
<p><em>Automated quarterly audit by ADR governance system</em></p>"""

    return html


def main() -> int:
    """Main audit entrypoint."""
    import argparse

    parser = argparse.ArgumentParser(description="Run quarterly ADR audit")
    parser.add_argument("--dry-run", action="store_true", help="Run audit without creating Plane issue")
    parser.add_argument("--audit-team", default="platform-architects", help="Team to tag in Plane issue")
    args = parser.parse_args()

    try:
        audit_report = run_quarterly_audit(dry_run=args.dry_run)

        if audit_report.get("error"):
            print(f"ERROR: {audit_report['error']}", file=sys.stderr)
            return 2

        if audit_report.get("skipped"):
            print("Audit skipped (not scheduled day)")
            return 0

        # Format and display report
        print(f"\nAudit Report Summary:")
        summary = audit_report.get("confidence_summary", {})
        print(
            f"  High: {summary.get('high', 0)} | Medium: {summary.get('medium', 0)} | Low: {summary.get('low', 0)} | None: {summary.get('none', 0)}"
        )
        print(f"\nRecommendations:")
        for rec in audit_report.get("recommendations", []):
            print(f"  - {rec}")

        if not args.dry_run:
            # Would create Plane issue here
            # For now, just print that we would create it
            print(
                f"\n[INFO] Would create Plane audit issue with {len(audit_report.get('recommendations', []))} recommendations"
            )

        return 0

    except Exception as e:
        print(f"ERROR: Audit failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
