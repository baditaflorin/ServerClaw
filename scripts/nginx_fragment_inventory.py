#!/usr/bin/env python3
"""
Nginx Fragment Inventory Management Tool

ADR 0350: Nginx Fragment-Based Atomic Configuration

Provides operational commands for inspecting, validating, and managing
nginx fragment files in the /etc/nginx/fragments.d/ directory.

Commands:
  list --vmid <id>                     List all fragments with metadata
  validate --vmid <id>                 Dry-run nginx -t on full config
  diff --vmid <id> --service <name>    Compare pending vs applied fragment
  orphans --vmid <id>                  Detect fragments with no running service

Exit codes (ADR 0343):
  0 — Success
  1 — Error (malformed args, IO failure, validation failure)
  2 — No-op (orphan list empty, no diff found, no validation errors)
  3 — Not found (service not found, fragment not found)
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class FragmentMetadata:
    """Metadata extracted from a fragment file."""
    filename: str
    path: Path
    adr_number: Optional[str]
    service_name: Optional[str]
    size_bytes: int
    modified_time: str
    managed_by: Optional[str]
    workstream: Optional[str]
    applied: Optional[str]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Nginx fragment inventory management tool (ADR 0350)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list --vmid 101
  %(prog)s validate --vmid 101
  %(prog)s diff --vmid 101 --service keycloak
  %(prog)s orphans --vmid 101
        """,
    )

    # Global options
    parser.add_argument(
        "--vmid",
        type=int,
        help="Target VM ID (stored in role defaults or passed directly)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List all fragments")
    list_parser.add_argument("--vmid", type=int, required=True, help="VM ID")
    list_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    # validate subcommand
    validate_parser = subparsers.add_parser(
        "validate", help="Validate nginx config"
    )
    validate_parser.add_argument("--vmid", type=int, required=True, help="VM ID")

    # diff subcommand
    diff_parser = subparsers.add_parser(
        "diff", help="Diff pending vs applied fragment"
    )
    diff_parser.add_argument("--vmid", type=int, required=True, help="VM ID")
    diff_parser.add_argument(
        "--service", type=str, required=True, help="Service name"
    )

    # orphans subcommand
    orphans_parser = subparsers.add_parser(
        "orphans", help="Detect orphan fragments"
    )
    orphans_parser.add_argument("--vmid", type=int, required=True, help="VM ID")
    orphans_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    args = parser.parse_args()

    # At least one subcommand is required
    if not args.command:
        parser.print_help()
        sys.exit(1)

    return args


def get_fragment_dir() -> Path:
    """Get nginx fragments directory path."""
    return Path("/etc/nginx/fragments.d")


def extract_fragment_metadata(fragment_file: Path) -> FragmentMetadata:
    """Extract metadata from a fragment file."""
    adr_number = None
    service_name = None

    # Parse filename: <adr>-<service>.conf
    match = re.match(r"(\d{4})-([a-z0-9_-]+)\.conf", fragment_file.name)
    if match:
        adr_number = match.group(1)
        service_name = match.group(2)

    # Parse provenance header from file content
    managed_by = None
    workstream = None
    applied = None

    try:
        with open(fragment_file, "r") as f:
            for line in f:
                if "Managed by:" in line:
                    managed_by = line.split("Managed by:")[-1].strip()
                elif "Workstream:" in line:
                    workstream = line.split("Workstream:")[-1].strip()
                elif "Applied:" in line:
                    applied = line.split("Applied:")[-1].strip()
                # Only check first 10 lines for headers
                if line.strip() and not line.startswith("#"):
                    break
    except Exception:
        pass

    stat_info = fragment_file.stat()
    modified_time = datetime.fromtimestamp(
        stat_info.st_mtime
    ).isoformat()

    return FragmentMetadata(
        filename=fragment_file.name,
        path=fragment_file,
        adr_number=adr_number,
        service_name=service_name,
        size_bytes=stat_info.st_size,
        modified_time=modified_time,
        managed_by=managed_by,
        workstream=workstream,
        applied=applied,
    )


def list_fragments(vmid: int, as_json: bool = False) -> int:
    """List all fragments on a VM."""
    frag_dir = get_fragment_dir()

    if not frag_dir.exists():
        print(f"Error: Fragment directory not found: {frag_dir}", file=sys.stderr)
        return 1

    # Collect all fragments
    fragments = []
    for fragment_file in sorted(frag_dir.glob("*.conf")):
        metadata = extract_fragment_metadata(fragment_file)
        fragments.append(metadata)

    if not fragments:
        print(f"No fragments found in {frag_dir}")
        return 2

    if as_json:
        output = [
            {
                "filename": f.filename,
                "adr": f.adr_number or "unknown",
                "service": f.service_name or "unknown",
                "size_bytes": f.size_bytes,
                "modified": f.modified_time,
                "managed_by": f.managed_by or "unknown",
                "workstream": f.workstream or "unknown",
                "applied": f.applied or "unknown",
            }
            for f in fragments
        ]
        print(json.dumps(output, indent=2))
    else:
        # Table format
        print(f"{'Filename':<35} {'ADR':<6} {'Service':<20} {'Size':<10} {'Modified':<25}")
        print("-" * 95)
        for f in fragments:
            adr_str = f.adr_number or "???"
            service_str = f.service_name or "???"
            size_str = f"{f.size_bytes} B"
            print(
                f"{f.filename:<35} {adr_str:<6} {service_str:<20} {size_str:<10} {f.modified_time:<25}"
            )
        print(f"\nTotal: {len(fragments)} fragments")

    return 0


def validate_nginx(vmid: int) -> int:
    """Validate nginx config with a dry-run of nginx -t."""
    try:
        result = subprocess.run(
            ["nginx", "-t", "-c", "/etc/nginx/nginx.conf"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            print("nginx configuration is valid")
            return 0
        else:
            print("nginx validation failed:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return 1

    except FileNotFoundError:
        print(
            "Error: nginx binary not found. Is nginx installed?",
            file=sys.stderr,
        )
        return 1
    except subprocess.TimeoutExpired:
        print("Error: nginx -t timed out after 10 seconds", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error running nginx -t: {e}", file=sys.stderr)
        return 1


def diff_fragment(vmid: int, service_name: str) -> int:
    """Show diff between pending and applied fragment."""
    frag_dir = get_fragment_dir()

    # Find the fragment file
    matching_fragments = list(frag_dir.glob(f"*-{service_name}.conf"))

    if not matching_fragments:
        print(f"Error: No fragment found for service '{service_name}'", file=sys.stderr)
        return 3

    fragment_file = matching_fragments[0]
    staging_file = fragment_file.parent / f".{fragment_file.name}.tmp"

    if not staging_file.exists():
        print(f"No pending changes for service '{service_name}'")
        return 2

    # Simple diff output
    try:
        with open(fragment_file, "r") as f:
            applied_content = f.read()
        with open(staging_file, "r") as f:
            pending_content = f.read()

        if applied_content == pending_content:
            print(f"No differences for service '{service_name}'")
            return 2

        print(f"Differences for service '{service_name}':")
        print("-" * 50)
        print("Applied version:")
        print(applied_content[:500])
        print("\n--- (truncated)")
        print("\nPending version:")
        print(pending_content[:500])
        print("--- (truncated)")
        return 0

    except Exception as e:
        print(f"Error reading fragment files: {e}", file=sys.stderr)
        return 1


def detect_orphans(vmid: int, as_json: bool = False) -> int:
    """Detect fragments with no corresponding running container."""
    frag_dir = get_fragment_dir()

    if not frag_dir.exists():
        print(f"Error: Fragment directory not found: {frag_dir}", file=sys.stderr)
        return 1

    # Collect all fragments
    fragments = []
    for fragment_file in sorted(frag_dir.glob("*.conf")):
        metadata = extract_fragment_metadata(fragment_file)
        fragments.append(metadata)

    if not fragments:
        print("No fragments found")
        return 2

    # Check which services are running via docker ps
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        running_containers = set(result.stdout.strip().split("\n"))
    except Exception:
        # If docker is not available, assume no orphans can be detected
        running_containers = set()

    # Find orphans
    orphans = []
    for f in fragments:
        if f.service_name and f.service_name not in running_containers:
            orphans.append(f)

    if not orphans:
        print("No orphan fragments detected")
        return 2

    if as_json:
        output = [
            {
                "filename": f.filename,
                "adr": f.adr_number or "unknown",
                "service": f.service_name or "unknown",
            }
            for f in orphans
        ]
        print(json.dumps(output, indent=2))
    else:
        print(f"Found {len(orphans)} orphan fragment(s):")
        print("-" * 60)
        for f in orphans:
            adr_str = f.adr_number or "???"
            service_str = f.service_name or "???"
            print(f"  {f.filename:<35} ADR {adr_str} ({service_str})")

    return 0


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.command == "list":
        return list_fragments(args.vmid, as_json=args.json)
    elif args.command == "validate":
        return validate_nginx(args.vmid)
    elif args.command == "diff":
        return diff_fragment(args.vmid, args.service)
    elif args.command == "orphans":
        return detect_orphans(args.vmid, as_json=args.json)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
