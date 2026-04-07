#!/usr/bin/env python3
"""
ADR Implementation Status Scanner — WS-0401

Scans git history, codebase structure, and configuration to detect implementation
markers for ADRs and generate status reports that can be compared against the
ADR index claims.

Design:
  1. Parse ADR index to load canonical metadata (implementation_status, etc.)
  2. Scan git history for commits referencing ADR numbers
  3. Search for role/playbook/config files with ADR-derived names
  4. Detect implementation markers: Ansible roles, Docker Compose, playbooks, etc.
  5. Generate reports showing actual vs. claimed implementation status
  6. Output machine-readable YAML and human-friendly markdown

Usage:
  python scripts/adr_implementation_scanner.py --adr-numbers 0024,0025,0058,0061 --output docs/adr/implementation-status/
  python scripts/adr_implementation_scanner.py --scan-all --output docs/adr/implementation-status/
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
import json
import re
import subprocess
import sys
from typing import Any
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "adr"
INDEX_PATH = ADR_DIR / ".index.yaml"
SCRIPTS_DIR = REPO_ROOT / "scripts"
COLLECTIONS_DIR = REPO_ROOT / "collections"
PLAYBOOKS_DIR = REPO_ROOT / "playbooks"


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class ADRMetadata:
    """Canonical ADR metadata from the index."""
    adr_number: str
    title: str
    filename: str
    path: str
    status: str
    implementation_status: str
    implemented_in_repo_version: str | None = None
    implemented_in_platform_version: str | None = None
    implemented_on: str | None = None
    concern: str | None = None
    date: str | None = None


@dataclass
class ImplementationMarker:
    """Detected implementation marker in the repository."""
    marker_type: str  # "git-commit", "ansible-role", "playbook", "compose-file", "config-file"
    adr_number: str
    location: str
    evidence: str
    confidence: float  # 0.0 to 1.0
    detected_on: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ADRImplementationReport:
    """Full implementation report for an ADR."""
    adr_number: str
    title: str
    canonical_status: str
    canonical_implementation_status: str
    detected_markers: list[ImplementationMarker]
    inferred_implementation_status: str
    status_match: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "adr_number": self.adr_number,
            "title": self.title,
            "canonical_status": self.canonical_status,
            "canonical_implementation_status": self.canonical_implementation_status,
            "detected_markers": [asdict(m) for m in self.detected_markers],
            "inferred_implementation_status": self.inferred_implementation_status,
            "status_match": self.status_match,
            "summary": self.summary,
        }


# ==============================================================================
# ADR Index Loader
# ==============================================================================

def load_adr_index() -> dict[str, ADRMetadata]:
    """Load ADR metadata from the generated index shards."""
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"ADR index not found at {INDEX_PATH}")

    metadata: dict[str, ADRMetadata] = {}

    # Load the range-based index shards
    index_dir = ADR_DIR / "index" / "by-range"
    for shard_file in sorted(index_dir.glob("*.yaml")):
        with open(shard_file) as f:
            shard = yaml.safe_load(f)

        if not shard or "adrs" not in shard:
            continue

        for adr_entry in shard["adrs"]:
            adr_num = str(adr_entry["adr"]).zfill(4)
            metadata[adr_num] = ADRMetadata(
                adr_number=adr_num,
                title=adr_entry.get("title", ""),
                filename=adr_entry.get("filename", ""),
                path=adr_entry.get("path", ""),
                status=adr_entry.get("status", "Unknown"),
                implementation_status=adr_entry.get("implementation_status", "Unknown"),
                implemented_in_repo_version=adr_entry.get("implemented_in_repo_version"),
                implemented_in_platform_version=adr_entry.get("implemented_in_platform_version"),
                implemented_on=adr_entry.get("implemented_on"),
                concern=adr_entry.get("concern"),
                date=adr_entry.get("date"),
            )

    return metadata


# ==============================================================================
# Git History Scanner
# ==============================================================================

def scan_git_history(adr_number: str) -> list[ImplementationMarker]:
    """Scan git history for commits referencing an ADR number."""
    markers: list[ImplementationMarker] = []

    # Patterns to match ADR references
    patterns = [
        rf"\bADR\s+{adr_number}\b",
        rf"\badr[_-]?{adr_number}\b",
        rf"\b{adr_number}\b",  # Just the number (lower confidence)
    ]

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--all"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return markers

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            # Try each pattern with decreasing confidence
            for idx, pattern in enumerate(patterns):
                if re.search(pattern, line, re.IGNORECASE):
                    confidence = 1.0 - (idx * 0.2)  # 1.0, 0.8, 0.6
                    commit_hash = line.split()[0]
                    markers.append(
                        ImplementationMarker(
                            marker_type="git-commit",
                            adr_number=adr_number,
                            location=f"git:{commit_hash}",
                            evidence=line,
                            confidence=confidence,
                        )
                    )
                    break  # Use highest-confidence pattern match

        return markers

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return markers


# ==============================================================================
# Repository Structure Scanner
# ==============================================================================

def scan_ansible_roles(adr_number: str) -> list[ImplementationMarker]:
    """Detect Ansible roles with ADR-derived names."""
    markers: list[ImplementationMarker] = []

    if not COLLECTIONS_DIR.exists():
        return markers

    roles_dir = COLLECTIONS_DIR / "ansible_collections" / "lv3" / "platform" / "roles"
    if not roles_dir.exists():
        return markers

    # Check for roles with ADR-related names
    # Convert ADR number to potential role names
    adr_keywords = [
        f"adr{adr_number}",
        f"adr_{adr_number}",
        f"adr-{adr_number}",
    ]

    for role_dir in roles_dir.iterdir():
        if not role_dir.is_dir():
            continue

        role_name = role_dir.name.lower()

        # Check for direct ADR reference in role name
        for keyword in adr_keywords:
            if keyword in role_name:
                markers.append(
                    ImplementationMarker(
                        marker_type="ansible-role",
                        adr_number=adr_number,
                        location=str(role_dir.relative_to(REPO_ROOT)),
                        evidence=f"Role {role_name} contains ADR reference",
                        confidence=0.9,
                    )
                )
                break

        # Check for ADR references in role metadata files
        meta_file = role_dir / "meta" / "main.yml"
        if meta_file.exists():
            with open(meta_file) as f:
                content = f.read()
                if re.search(rf"\badr[_-]?{adr_number}\b", content, re.IGNORECASE):
                    markers.append(
                        ImplementationMarker(
                            marker_type="ansible-role",
                            adr_number=adr_number,
                            location=str(meta_file.relative_to(REPO_ROOT)),
                            evidence=f"ADR reference found in role metadata",
                            confidence=0.85,
                        )
                    )

    return markers


def scan_playbooks(adr_number: str) -> list[ImplementationMarker]:
    """Detect playbooks with ADR-derived names or references."""
    markers: list[ImplementationMarker] = []

    if not PLAYBOOKS_DIR.exists():
        return markers

    adr_patterns = [
        rf"\badr[_-]?{adr_number}\b",
        rf"\bADR\s+{adr_number}\b",
    ]

    for playbook_file in PLAYBOOKS_DIR.glob("*.yml"):
        with open(playbook_file) as f:
            content = f.read()

        for pattern in adr_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                markers.append(
                    ImplementationMarker(
                        marker_type="playbook",
                        adr_number=adr_number,
                        location=str(playbook_file.relative_to(REPO_ROOT)),
                        evidence=f"ADR reference found in playbook",
                        confidence=0.9,
                    )
                )
                break

    return markers


def scan_compose_files(adr_number: str) -> list[ImplementationMarker]:
    """Detect Docker Compose files with ADR-derived names or references."""
    markers: list[ImplementationMarker] = []

    adr_patterns = [
        rf"\badr[_-]?{adr_number}\b",
        rf"\bADR\s+{adr_number}\b",
    ]

    # Search under collections and playbooks
    for search_dir in [COLLECTIONS_DIR, PLAYBOOKS_DIR]:
        if not search_dir.exists():
            continue

        for compose_file in search_dir.rglob("docker-compose*.y*ml"):
            with open(compose_file) as f:
                content = f.read()

            for pattern in adr_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    markers.append(
                        ImplementationMarker(
                            marker_type="compose-file",
                            adr_number=adr_number,
                            location=str(compose_file.relative_to(REPO_ROOT)),
                            evidence="ADR reference found in Compose file",
                            confidence=0.85,
                        )
                    )
                    break

    return markers


def scan_config_files(adr_number: str) -> list[ImplementationMarker]:
    """Detect configuration files with ADR-derived names or references."""
    markers: list[ImplementationMarker] = []

    # Search for config files that mention the ADR
    adr_pattern = rf"\badr[_-]?{adr_number}\b"

    # Search common config directories
    search_patterns = [
        REPO_ROOT / "config" / "*.json",
        REPO_ROOT / "config" / "*.yml",
        REPO_ROOT / "config" / "*.yaml",
    ]

    for pattern in search_patterns:
        for config_file in REPO_ROOT.glob(str(pattern).replace(str(REPO_ROOT), "").lstrip("/")):
            if not config_file.is_file():
                continue

            try:
                with open(config_file) as f:
                    content = f.read()
                    if re.search(adr_pattern, content, re.IGNORECASE):
                        markers.append(
                            ImplementationMarker(
                                marker_type="config-file",
                                adr_number=adr_number,
                                location=str(config_file.relative_to(REPO_ROOT)),
                                evidence="ADR reference found in config file",
                                confidence=0.8,
                            )
                        )
            except (IsADirectoryError, UnicodeDecodeError):
                pass

    return markers


# ==============================================================================
# Infer Implementation Status
# ==============================================================================

def infer_implementation_status(markers: list[ImplementationMarker]) -> str:
    """Infer implementation status from detected markers."""
    if not markers:
        return "No Evidence"

    # Count marker types and calculate confidence score
    high_confidence_markers = [m for m in markers if m.confidence >= 0.85]
    medium_confidence_markers = [m for m in markers if 0.6 <= m.confidence < 0.85]

    git_markers = [m for m in markers if m.marker_type == "git-commit"]
    structural_markers = [
        m for m in markers if m.marker_type in ["ansible-role", "playbook", "compose-file", "config-file"]
    ]

    # Heuristics for inferring status
    if len(high_confidence_markers) >= 3 or (len(git_markers) >= 5 and len(structural_markers) >= 2):
        return "Likely Implemented"

    if len(high_confidence_markers) >= 1 or len(git_markers) >= 3:
        return "Possibly Implemented"

    if len(markers) >= 1:
        return "Partial Evidence"

    return "No Evidence"


# ==============================================================================
# Report Generation
# ==============================================================================

def generate_report(
    adr_metadata: ADRMetadata,
    markers: list[ImplementationMarker],
) -> ADRImplementationReport:
    """Generate a complete implementation report for an ADR."""
    inferred_status = infer_implementation_status(markers)
    canonical_status = adr_metadata.implementation_status

    # Check if inferred status matches canonical
    status_match = (
        (canonical_status == "Implemented" and inferred_status.startswith("Likely"))
        or (canonical_status == "Partial" and inferred_status == "Partial Evidence")
        or (canonical_status == "Not Implemented" and inferred_status == "No Evidence")
    )

    # Generate summary
    summary_lines = [
        f"Canonical Status: {canonical_status}",
        f"Inferred Status: {inferred_status}",
        f"Markers Found: {len(markers)}",
    ]

    if markers:
        marker_summary = {}
        for marker in markers:
            marker_summary[marker.marker_type] = marker_summary.get(marker.marker_type, 0) + 1

        summary_lines.append(f"Breakdown: {', '.join(f'{k}={v}' for k, v in marker_summary.items())}")

    if adr_metadata.implemented_on:
        summary_lines.append(f"Implemented On: {adr_metadata.implemented_on}")

    return ADRImplementationReport(
        adr_number=adr_metadata.adr_number,
        title=adr_metadata.title,
        canonical_status=adr_metadata.status,
        canonical_implementation_status=canonical_status,
        detected_markers=markers,
        inferred_implementation_status=inferred_status,
        status_match=status_match,
        summary="\n".join(summary_lines),
    )


# ==============================================================================
# Output Generation
# ==============================================================================

def generate_markdown_report(report: ADRImplementationReport) -> str:
    """Generate a human-readable markdown report."""
    lines = [
        f"# ADR {report.adr_number}: {report.title}",
        "",
        "## Implementation Status Summary",
        "",
        f"| Field | Value |",
        f"| --- | --- |",
        f"| Canonical Status | {report.canonical_implementation_status} |",
        f"| Inferred Status | {report.inferred_implementation_status} |",
        f"| Status Match | {'✓' if report.status_match else '✗'} |",
        f"| Markers Found | {len(report.detected_markers)} |",
        "",
    ]

    if report.detected_markers:
        lines.extend([
            "## Detected Implementation Markers",
            "",
        ])

        # Group by marker type
        by_type = {}
        for marker in report.detected_markers:
            if marker.marker_type not in by_type:
                by_type[marker.marker_type] = []
            by_type[marker.marker_type].append(marker)

        for marker_type in sorted(by_type.keys()):
            lines.append(f"### {marker_type.replace('_', ' ').title()}")
            lines.append("")

            for marker in by_type[marker_type]:
                lines.append(f"- **Location**: `{marker.location}`")
                lines.append(f"  - Evidence: {marker.evidence}")
                lines.append(f"  - Confidence: {marker.confidence:.0%}")
                lines.append("")

    else:
        lines.extend([
            "## Detected Implementation Markers",
            "",
            "No implementation markers detected.",
            "",
        ])

    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def write_yaml_report(report: ADRImplementationReport, output_dir: Path) -> Path:
    """Write YAML report to disk."""
    output_file = output_dir / f"adr-{report.adr_number}.yaml"
    with open(output_file, "w") as f:
        yaml.dump(report.to_dict(), f, default_flow_style=False, sort_keys=False)
    return output_file


def write_markdown_report(report: ADRImplementationReport, output_dir: Path) -> Path:
    """Write markdown report to disk."""
    output_file = output_dir / f"adr-{report.adr_number}.md"
    markdown = generate_markdown_report(report)
    with open(output_file, "w") as f:
        f.write(markdown)
    return output_file


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Scan ADR implementations and generate status reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--adr-numbers",
        help="Comma-separated list of ADR numbers to scan (e.g., 0024,0025,0058,0061)",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Scan all ADRs in the index",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ADR_DIR / "implementation-status",
        help="Output directory for reports",
    )
    parser.add_argument(
        "--format",
        choices=["yaml", "markdown", "both"],
        default="both",
        help="Output format(s)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.adr_numbers and not args.scan_all:
        parser.print_help()
        print("\nError: Specify either --adr-numbers or --scan-all", file=sys.stderr)
        sys.exit(1)

    # Load ADR index
    print("Loading ADR index...", file=sys.stderr)
    adr_index = load_adr_index()
    print(f"Loaded {len(adr_index)} ADRs", file=sys.stderr)

    # Determine which ADRs to scan
    if args.scan_all:
        adr_numbers = sorted(adr_index.keys())
    else:
        adr_numbers = [n.zfill(4) for n in args.adr_numbers.split(",")]

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Generate reports
    reports: list[ADRImplementationReport] = []
    print(f"Scanning {len(adr_numbers)} ADRs...", file=sys.stderr)

    for adr_number in adr_numbers:
        if adr_number not in adr_index:
            print(f"Warning: ADR {adr_number} not found in index", file=sys.stderr)
            continue

        metadata = adr_index[adr_number]
        print(f"  Scanning ADR {adr_number}...", file=sys.stderr)

        # Scan all implementation markers
        markers: list[ImplementationMarker] = []
        markers.extend(scan_git_history(adr_number))
        markers.extend(scan_ansible_roles(adr_number))
        markers.extend(scan_playbooks(adr_number))
        markers.extend(scan_compose_files(adr_number))
        markers.extend(scan_config_files(adr_number))

        # Generate report
        report = generate_report(metadata, markers)
        reports.append(report)

        # Write output
        if args.format in ["yaml", "both"]:
            write_yaml_report(report, args.output)

        if args.format in ["markdown", "both"]:
            write_markdown_report(report, args.output)

    # Generate index file
    index_data = {
        "scanner_version": "1.0",
        "generated": datetime.now().isoformat(),
        "total_adrs": len(reports),
        "scan_summary": {
            "fully_matching": len([r for r in reports if r.status_match and r.inferred_implementation_status == "Likely Implemented"]),
            "partial_matching": len([r for r in reports if r.detected_markers]),
            "no_evidence": len([r for r in reports if not r.detected_markers]),
        },
        "reports": [r.adr_number for r in reports],
    }

    with open(args.output / "INDEX.yaml", "w") as f:
        yaml.dump(index_data, f, default_flow_style=False, sort_keys=False)

    print(f"\nGenerated {len(reports)} reports in {args.output}", file=sys.stderr)
    print(f"Summary: {index_data['scan_summary']}", file=sys.stderr)


if __name__ == "__main__":
    main()
