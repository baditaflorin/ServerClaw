#!/usr/bin/env python3
"""Audit publication-sanitization.yaml for drift against authoritative sources.

Parses the real inventory (identity, hosts, host_vars, operators) to extract
all sensitive values, then verifies each has a matching replacement pattern
in the sanitization config.

Usage:
    python3 scripts/audit_sanitization_coverage.py            # report gaps
    python3 scripts/audit_sanitization_coverage.py --strict    # exit 1 on any gap
    python3 scripts/audit_sanitization_coverage.py --json      # machine-readable output
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "publication-sanitization.yaml"

# Authoritative source paths (relative to repo root)
IDENTITY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "identity.yml"
HOSTS_PATH = REPO_ROOT / "inventory" / "hosts.yml"
OPERATORS_PATH = REPO_ROOT / "config" / "operators.yaml"

# Detect host_vars file dynamically (name may vary per deployment)
HOST_VARS_DIR = REPO_ROOT / "inventory" / "host_vars"

# IP patterns
IPV4_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
IPV6_RE = re.compile(r"(?i)\b([0-9a-f:]{6,39})\b")

# RFC 5737 / documentation-range IPs that are safe (not sensitive)
DOC_IPV4_NETWORKS = [
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
]
DOC_IPV6_NETWORKS = [
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
]

# Private/internal ranges — tracked but lower severity
PRIVATE_IPV4_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT / Tailscale
    ipaddress.ip_network("127.0.0.0/8"),
]

# IPs that are never sensitive (bind addresses, broadcast, link-local, masks)
IGNORE_IPS = frozenset(
    {
        "0.0.0.0",
        "255.255.255.255",
        "255.255.255.0",
        "255.255.255.192",
        "255.255.255.128",
        "255.255.255.252",
        "255.255.0.0",
        "255.0.0.0",
    }
)

# Jinja2 template markers — skip values that are templates
JINJA2_RE = re.compile(r"\{\{.*\}\}")

# Deployment-specific suffixes/prefixes to flag in hostnames
DEPLOYMENT_MARKERS = ["-lv3", "proxmox_florin", "proxmox-florin"]


@dataclass
class SensitiveValue:
    value: str
    source: str
    category: str  # domain, pii, hostname, public_ip, private_ip
    severity: str  # CRITICAL, WARNING, INFO

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "source": self.source,
            "category": self.category,
            "severity": self.severity,
        }


def is_documentation_ipv4(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in DOC_IPV4_NETWORKS)


def is_private_ipv4(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in PRIVATE_IPV4_NETWORKS)


def is_documentation_ipv6(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in DOC_IPV6_NETWORKS)


def is_jinja2(value: str) -> bool:
    return bool(JINJA2_RE.search(value))


def is_placeholder(value: str) -> bool:
    placeholders = {
        "example.com",
        "operator@example.com",
        "Platform Operator",
        "example-admin",
        "Example Operator",
        "your-proxmox-host",
    }
    if value in placeholders:
        return True
    lower = value.lower()
    return "yourname" in lower or "CHANGE" in value or lower.startswith("example") or "your-" in lower


def is_deployment_specific(hostname: str) -> bool:
    return any(marker in hostname for marker in DEPLOYMENT_MARKERS)


def walk_host_keys(data: dict, path: str = "") -> list[str]:
    """Recursively extract all Ansible inventory hostnames from parsed YAML."""
    hostnames = []
    if not isinstance(data, dict):
        return hostnames

    for key, value in data.items():
        if key == "hosts" and isinstance(value, dict):
            hostnames.extend(value.keys())
        elif key == "children" and isinstance(value, dict):
            for child_name, child_data in value.items():
                if isinstance(child_data, dict):
                    hostnames.extend(walk_host_keys(child_data, f"{path}/{child_name}"))
        elif isinstance(value, dict):
            hostnames.extend(walk_host_keys(value, f"{path}/{key}"))

    return hostnames


def walk_string_values(data, path: str = "") -> list[tuple[str, str]]:
    """Recursively extract all string values from nested YAML, with path context."""
    results = []
    if isinstance(data, dict):
        for k, v in data.items():
            results.extend(walk_string_values(v, f"{path}.{k}"))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            results.extend(walk_string_values(v, f"{path}[{i}]"))
    elif isinstance(data, str):
        results.append((data, path))
    return results


def extract_sensitive_values() -> list[SensitiveValue]:
    """Parse authoritative sources and extract all sensitive values."""
    values: list[SensitiveValue] = []
    seen: set[str] = set()

    def add(value: str, source: str, category: str, severity: str) -> None:
        if value in seen or not value or is_jinja2(value) or is_placeholder(value):
            return
        seen.add(value)
        values.append(SensitiveValue(value, source, category, severity))

    # --- 1. identity.yml ---
    if IDENTITY_PATH.exists():
        identity = yaml.safe_load(IDENTITY_PATH.read_text())
        if identity:
            domain = identity.get("platform_domain", "")
            email = identity.get("platform_operator_email", "")
            name = identity.get("platform_operator_name", "")

            if domain and domain != "example.com":
                add(domain, "identity.yml", "domain", "CRITICAL")
            if email and "example.com" not in email:
                add(email, "identity.yml", "pii", "CRITICAL")
            if name and name != "Platform Operator":
                add(name, "identity.yml", "pii", "CRITICAL")

    # --- 2. hosts.yml ---
    if HOSTS_PATH.exists():
        hosts = yaml.safe_load(HOSTS_PATH.read_text())
        if hosts:
            # Extract hostnames from inventory structure
            hostnames = walk_host_keys(hosts)
            for h in set(hostnames):
                if is_deployment_specific(h):
                    add(h, "hosts.yml", "hostname", "WARNING")

            # Also scan string values for VM references in pattern mappings
            for val, path in walk_string_values(hosts):
                if is_deployment_specific(val) and not is_jinja2(val):
                    add(val, f"hosts.yml:{path}", "hostname", "WARNING")

    # --- 3. host_vars ---
    if HOST_VARS_DIR.exists():
        for hv_file in HOST_VARS_DIR.glob("*.yml"):
            text = hv_file.read_text(encoding="utf-8", errors="replace")
            fname = hv_file.name

            # Extract public IPv4 addresses
            for match in IPV4_RE.finditer(text):
                ip = match.group(1)
                if ip in IGNORE_IPS:
                    continue
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    continue
                if is_documentation_ipv4(ip):
                    continue
                if is_private_ipv4(ip):
                    add(ip, fname, "private_ip", "INFO")
                else:
                    add(ip, fname, "public_ip", "CRITICAL")

            # Extract IPv6 addresses (only obvious ones with multiple colons)
            for match in IPV6_RE.finditer(text):
                ip6 = match.group(1)
                if ip6.count(":") < 2:
                    continue
                try:
                    addr = ipaddress.ip_address(ip6)
                except ValueError:
                    continue
                if is_documentation_ipv6(ip6):
                    continue
                # Skip link-local (fe80::) and loopback (::1)
                if addr.is_link_local or addr.is_loopback:
                    continue
                add(ip6, fname, "public_ip", "CRITICAL")

    # --- 4. operators.yaml ---
    if OPERATORS_PATH.exists():
        operators = yaml.safe_load(OPERATORS_PATH.read_text())
        if operators:
            for op in operators.get("operators", []):
                if not isinstance(op, dict):
                    continue
                for field in ["name", "email"]:
                    val = op.get(field, "")
                    if val and not is_placeholder(val):
                        add(val, "operators.yaml", "pii", "CRITICAL")
                # Nested PII
                keycloak = op.get("keycloak", {})
                if isinstance(keycloak, dict):
                    for field in ["username"]:
                        val = keycloak.get(field, "")
                        if val and not is_placeholder(val):
                            add(val, "operators.yaml", "pii", "WARNING")
                tailscale = op.get("tailscale", {})
                if isinstance(tailscale, dict):
                    val = tailscale.get("login_email", "")
                    if val and not is_placeholder(val):
                        add(val, "operators.yaml", "pii", "CRITICAL")

    return values


def check_coverage(values: list[SensitiveValue], config: dict) -> tuple[list[SensitiveValue], list[SensitiveValue]]:
    """Check which values are covered by sanitization patterns.

    A value is covered if a string_replacement pattern matches it.
    Even values extracted from Tier A files need pattern coverage,
    because the same values appear throughout the codebase in non-Tier-A files.

    Returns (covered, gaps).
    """
    patterns = []
    for entry in config.get("string_replacements", []):
        patterns.append(re.compile(entry["pattern"]))

    covered = []
    gaps = []

    for sv in values:
        # Check if any string_replacement pattern matches
        matched = False
        for pat in patterns:
            if pat.search(sv.value):
                matched = True
                break

        if matched:
            covered.append(sv)
        else:
            gaps.append(sv)

    return covered, gaps


def derive_leak_markers(values: list[SensitiveValue]) -> list[str]:
    """Generate leak markers from extracted sensitive values.

    Only CRITICAL values become leak markers — these are the values that
    must never appear in the sanitized output.
    """
    markers = set()
    for sv in values:
        if sv.severity == "CRITICAL":
            markers.add(sv.value)
    return sorted(markers)


def print_report(
    values: list[SensitiveValue],
    covered: list[SensitiveValue],
    gaps: list[SensitiveValue],
    config: dict,
) -> None:
    print("Sanitization Coverage Audit")
    print("=" * 60)
    print(f"\nExtracted {len(values)} sensitive values from authoritative sources")
    print(f"  Covered: {len(covered)}")
    print(f"  Gaps:    {len(gaps)}")

    critical = [g for g in gaps if g.severity == "CRITICAL"]
    warnings = [g for g in gaps if g.severity == "WARNING"]
    info = [g for g in gaps if g.severity == "INFO"]

    if critical:
        print(f"\nCRITICAL gaps ({len(critical)}) — would leak to public:")
        for g in critical:
            print(f"  {g.value:<40s} from {g.source:<25s} ({g.category})")

    if warnings:
        print(f"\nWARNING gaps ({len(warnings)}) — deployment-specific names:")
        for g in warnings:
            print(f"  {g.value:<40s} from {g.source:<25s} ({g.category})")

    if info:
        print(f"\nINFO ({len(info)}) — internal IPs (low risk):")
        for g in info[:10]:
            print(f"  {g.value:<40s} from {g.source:<25s} ({g.category})")
        if len(info) > 10:
            print(f"  ... and {len(info) - 10} more")

    # Compare auto-derived vs manual leak markers
    auto_markers = derive_leak_markers(values)
    manual_markers = config.get("leak_markers", [])
    auto_only = set(auto_markers) - set(manual_markers)
    manual_only = set(manual_markers) - set(auto_markers)

    print(f"\nLeak markers: {len(auto_markers)} auto-derived, {len(manual_markers)} manual")
    if auto_only:
        print(f"  Auto-derived but not in manual list ({len(auto_only)}):")
        for m in sorted(auto_only):
            print(f"    + {m}")
    if manual_only:
        print(f"  Manual-only (not auto-derived) ({len(manual_only)}):")
        for m in sorted(manual_only):
            print(f"    - {m}")

    if not gaps:
        print(f"\nAll {len(values)} sensitive values are covered.")
    else:
        print(f"\nSummary: {len(critical)} CRITICAL, {len(warnings)} WARNING, {len(info)} INFO")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit publication sanitization coverage for drift")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on any gap (CRITICAL or WARNING)",
    )
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    if not CONFIG_PATH.exists():
        print(f"ERROR: Config not found: {CONFIG_PATH}", file=sys.stderr)
        return 1

    config = yaml.safe_load(CONFIG_PATH.read_text())
    values = extract_sensitive_values()
    covered, gaps = check_coverage(values, config)

    if args.json:
        result = {
            "total": len(values),
            "covered": len(covered),
            "gaps": [g.as_dict() for g in gaps],
            "auto_leak_markers": derive_leak_markers(values),
        }
        print(json.dumps(result, indent=2))
    else:
        print_report(values, covered, gaps, config)

    critical = [g for g in gaps if g.severity == "CRITICAL"]
    warnings = [g for g in gaps if g.severity == "WARNING"]

    if critical:
        return 2  # CRITICAL gaps
    if args.strict and warnings:
        return 1  # strict mode fails on warnings too
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
