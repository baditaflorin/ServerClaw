#!/usr/bin/env python3
"""subdomain_tool.py — Query subdomain catalog and exposure registry.

Data sources:
  config/subdomain-catalog.json
  config/subdomain-exposure-registry.json

Commands
--------
  list                         List all reserved subdomain prefixes
  show   --prefix PREFIX       Show detail for one prefix
  exposed                      Show publicly exposed subdomains from the registry
  check  --fqdn FQDN           Check if an FQDN is in the catalog or exposure registry
  summary                      Overview of subdomain usage

Examples
--------
  python scripts/subdomain_tool.py list
  python scripts/subdomain_tool.py show --prefix gitea
  python scripts/subdomain_tool.py exposed
  python scripts/subdomain_tool.py check --fqdn git.localhost
  python scripts/subdomain_tool.py summary
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "config" / "subdomain-catalog.json"
REGISTRY = REPO_ROOT / "config" / "subdomain-exposure-registry.json"


def _load_catalog() -> dict:
    if not CATALOG.exists():
        return {}
    return json.loads(CATALOG.read_text())


def _load_registry() -> dict:
    if not REGISTRY.exists():
        return {}
    return json.loads(REGISTRY.read_text())


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    data = _load_catalog()
    prefixes = data.get("reserved_prefixes", [])
    publishing_rules = data.get("publishing_rules", {})
    print(f"{'PREFIX':<20}  {'ADR':<8}  {'ALLOWED_FQDNs':<40}  NOTES")
    print("-" * 110)
    for p in sorted(prefixes, key=lambda x: x.get("prefix", "")):
        fqdns = ", ".join(p.get("allowed_fqdns", []))
        notes = p.get("notes", "")[:50]
        print(f"{p.get('prefix',''):<20}  {p.get('owner_adr',''):<8}  {fqdns:<40}  {notes}")
    print(f"\n{len(prefixes)} reserved prefix(es)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    data = _load_catalog()
    prefixes = data.get("reserved_prefixes", [])
    prefix_lower = args.prefix.lower()
    match = next((p for p in prefixes if p.get("prefix", "").lower() == prefix_lower), None)
    if match is None:
        match = next(
            (p for p in prefixes if prefix_lower in p.get("prefix", "").lower()), None
        )
    if match is None:
        print(f"ERROR: prefix '{args.prefix}' not found in catalog")
        return 1
    print(json.dumps(match, indent=2))
    return 0


def cmd_exposed(args: argparse.Namespace) -> int:
    data = _load_registry()
    exposed = data.get("exposed_subdomains", [])
    if not exposed:
        print("No exposed subdomains in registry")
        return 0
    last_audit = data.get("last_audit", "unknown")
    print(f"Last audit: {last_audit}\n")
    print(f"{'FQDN':<40}  {'TIER':<10}  {'AUTH':<20}  NOTES")
    print("-" * 100)
    for sub in sorted(exposed, key=lambda x: x.get("fqdn", "")):
        print(
            f"{sub.get('fqdn',''):<40}  {sub.get('tier',''):<10}  "
            f"{sub.get('auth',''):<20}  {sub.get('notes','')[:40]}"
        )
    print(f"\n{len(exposed)} exposed subdomain(s)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    fqdn = args.fqdn.lower()
    catalog = _load_catalog()
    registry = _load_registry()

    # Check catalog prefixes
    in_catalog = False
    for p in catalog.get("reserved_prefixes", []):
        for allowed in p.get("allowed_fqdns", []):
            if allowed.lower() == fqdn:
                in_catalog = True
                print(f"CATALOG: Found as reserved prefix '{p['prefix']}' (ADR {p.get('owner_adr','?')})")
                break

    # Check exposure registry
    in_registry = False
    for sub in registry.get("exposed_subdomains", []):
        if sub.get("fqdn", "").lower() == fqdn:
            in_registry = True
            print(f"REGISTRY: Exposed — tier={sub.get('tier','?')} auth={sub.get('auth','?')}")
            break

    if not in_catalog and not in_registry:
        print(f"'{args.fqdn}' not found in catalog or exposure registry")
        return 1
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    catalog = _load_catalog()
    registry = _load_registry()
    prefixes = catalog.get("reserved_prefixes", [])
    exposed = registry.get("exposed_subdomains", [])
    last_audit = registry.get("last_audit", "unknown")

    print(f"Subdomain Summary\n")
    print(f"  Reserved prefixes  : {len(prefixes)}")
    total_fqdns = sum(len(p.get("allowed_fqdns", [])) for p in prefixes)
    print(f"  Declared FQDNs     : {total_fqdns}")
    print(f"  Exposed subdomains : {len(exposed)}")
    print(f"  Last audit         : {last_audit}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="subdomain_tool.py",
        description="Query subdomain catalog and exposure registry.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("list", help="List reserved subdomain prefixes")

    shp = sub.add_parser("show", help="Show one prefix entry")
    shp.add_argument("--prefix", required=True, metavar="PREFIX")

    sub.add_parser("exposed", help="Show publicly exposed subdomains")

    cp = sub.add_parser("check", help="Check if an FQDN is in the catalog")
    cp.add_argument("--fqdn", required=True, metavar="FQDN")

    sub.add_parser("summary", help="Subdomain usage overview")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "exposed": cmd_exposed,
        "check": cmd_check,
        "summary": cmd_summary,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
