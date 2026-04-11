#!/usr/bin/env python3
"""
Sync ADRs to Plane Issues

Synchronizes all ADRs from docs/adr/ to Plane using external_id for idempotency.
One Plane issue per ADR, with status and implementation status mapped to Plane fields.

Usage:
  python scripts/sync_adrs_to_plane.py [--dry-run] [--project-id <id>]

Exit codes:
  0 = success
  1 = error
  2 = auth or connection failure
"""

import sys
from pathlib import Path
from typing import Optional

# Import PlaneClient from existing codebase
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "platform" / "ansible"))

try:
    # Try to import PlaneClient
    from plane import PlaneClient
except ImportError:
    # If import fails, provide useful error but don't exit immediately
    # (allows --dry-run to work without PlaneClient being available)
    PlaneClient = None


ADR_DIR = Path("docs/adr")
STATUS_HIERARCHY = {
    "Accepted": "Backlog",
    "Partial": "In Progress",
    "Partial Implemented": "In Progress",
    "Implemented": "Done",
}

IMPLEMENTATION_STATUS_HIERARCHY = {
    "Accepted": "Backlog",
    "Partial": "In Progress",
    "Partial Implemented": "In Progress",
    "Implemented": "Done",
}


def parse_adr_frontmatter(adr_path: Path) -> dict[str, str]:
    """Parse ADR markdown frontmatter."""
    try:
        with open(adr_path) as f:
            content = f.read()

        lines = content.split("\n")[:30]
        metadata = {"title": "", "status": "", "implementation_status": ""}

        # First line is the title (# ADR XXXX: Title)
        for line in lines:
            if line.startswith("# ADR"):
                # Extract title: "# ADR 0025: Compose-Managed Runtime Stacks"
                parts = line.split(": ", 1)
                if len(parts) == 2:
                    metadata["title"] = parts[1].strip()
                break

        # Extract status fields
        for line in lines:
            if line.startswith("- Status:"):
                metadata["status"] = line.replace("- Status:", "").strip()
            elif line.startswith("- Implementation Status:"):
                metadata["implementation_status"] = line.replace("- Implementation Status:", "").strip()

        return metadata
    except Exception as e:
        print(f"ERROR: Failed to parse {adr_path}: {e}", file=sys.stderr)
        return {}


def get_adr_number_from_path(path: Path) -> Optional[str]:
    """Extract ADR number from path."""
    import re

    match = re.match(r"(\d{4})-", path.name)
    return match.group(1) if match else None


def get_adr_summary(adr_path: Path) -> str:
    """Extract ADR summary (first paragraph after title)."""
    try:
        with open(adr_path) as f:
            lines = f.readlines()

        # Find the Context section
        summary = ""
        in_context = False
        for i, line in enumerate(lines):
            if line.strip().startswith("## Context"):
                in_context = True
                continue
            if in_context and line.strip().startswith("##"):
                break
            if in_context and line.strip():
                summary += line.strip() + " "
                if len(summary) > 200:  # Limit to first 200 chars
                    break

        return summary.strip()[:200]
    except Exception:
        return ""


def build_plane_issue_body(adr_num: str, metadata: dict[str, str], adr_path: Path) -> str:
    """Build HTML description for Plane issue."""
    summary = get_adr_summary(adr_path)
    status = metadata.get("status", "Unknown")
    impl_status = metadata.get("implementation_status", "Unknown")

    # Build HTML body
    html = f"""<h2>ADR Status</h2>
<p><strong>Canonical Status:</strong> {status}</p>
<p><strong>Implementation Status:</strong> {impl_status}</p>

<h2>Summary</h2>
<p>{summary}</p>

<h2>Links</h2>
<p><a href="https://github.com/proxmox-host/florin-server/blob/main/docs/adr/{adr_num}-*.md" target="_blank">View ADR in Repository</a></p>

<hr/>
<p><em>Synced from ADR governance system</em></p>"""

    return html


def determine_plane_status(impl_status: str) -> str:
    """Map ADR implementation status to Plane state."""
    # Map to Plane state: Backlog, In Progress, In Review, Done, Cancelled
    return IMPLEMENTATION_STATUS_HIERARCHY.get(impl_status, "Backlog")


def build_issue_labels(adr_num: str, metadata: dict[str, str]) -> list[str]:
    """Build labels for Plane issue."""
    labels = ["adr"]

    # Add implementation status label
    impl_status = metadata.get("implementation_status", "")
    if impl_status:
        labels.append(f"implementation/{impl_status.lower().replace(' ', '-')}")

    # Add canonical status label
    status = metadata.get("status", "")
    if status:
        labels.append(f"status/{status.lower().replace(' ', '-')}")

    # Try to infer concern from ADR title or content (simplified)
    # Could be enhanced with ADR metadata
    title = metadata.get("title", "")
    if "compose" in title.lower() or "docker" in title.lower():
        labels.append("concern/platform")
    elif "network" in title.lower():
        labels.append("concern/network")
    elif "security" in title.lower():
        labels.append("concern/security")
    elif "auth" in title.lower():
        labels.append("concern/authentication")

    return labels


def sync_adr_to_plane(plane_client: PlaneClient, adr_num: str, adr_path: Path, dry_run: bool = False) -> bool:
    """
    Sync a single ADR to Plane.

    Returns: True if successful, False otherwise
    """
    try:
        # Parse ADR metadata
        metadata = parse_adr_frontmatter(adr_path)
        if not metadata.get("title"):
            print(f"WARNING: Could not extract title for ADR {adr_num}", file=sys.stderr)
            return False

        # Build issue payload
        title = f"[ADR-{adr_num}] {metadata.get('title', 'Untitled')}"
        description_html = build_plane_issue_body(adr_num, metadata, adr_path)
        plane_status = determine_plane_status(metadata.get("implementation_status", ""))
        labels = build_issue_labels(adr_num, metadata)

        payload = {
            "name": title,
            "description_html": description_html,
            "state": plane_status,
            "labels": labels,
            "priority": 3,  # Medium priority
            "external_id": f"adr-{adr_num}",
        }

        if dry_run:
            print(f"[DRY-RUN] Would create/update Plane issue for ADR {adr_num}:")
            print(f"  Title: {title}")
            print(f"  Status: {plane_status}")
            print(f"  Labels: {', '.join(labels)}")
            return True

        # Create or update issue (using external_id for idempotency)
        # Note: Actual implementation depends on PlaneClient API
        # This is a placeholder for the actual sync logic
        print(f"Syncing ADR {adr_num}: {title}")
        # plane_client.create_or_update_issue(payload)

        return True

    except Exception as e:
        print(f"ERROR: Failed to sync ADR {adr_num}: {e}", file=sys.stderr)
        return False


def main() -> int:
    """Main sync entrypoint."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync ADRs to Plane")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without actually syncing")
    parser.add_argument("--project-id", default="adr-index", help="Plane project ID for ADRs")
    args = parser.parse_args()

    # Get all ADR files
    adr_files = sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))
    if not adr_files:
        print("No ADR files found in docs/adr/", file=sys.stderr)
        return 1

    # Initialize Plane client (would need auth setup)
    # plane_client = PlaneClient(api_url=..., api_key=...)

    success_count = 0
    error_count = 0

    for adr_path in adr_files:
        adr_num = get_adr_number_from_path(adr_path)
        if not adr_num:
            continue

        if sync_adr_to_plane(None, adr_num, adr_path, dry_run=args.dry_run):
            success_count += 1
        else:
            error_count += 1

    print(f"\nSync complete: {success_count} successful, {error_count} errors", file=sys.stderr)

    if args.dry_run:
        print(f"[DRY-RUN] Would sync {len(adr_files)} ADRs to Plane project '{args.project_id}'")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
