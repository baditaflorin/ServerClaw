#!/usr/bin/env python3
"""
generate_adr_index.py — ADR 0164 / ADR 0168
============================================
Generate docs/adr/.index.yaml from the actual ADR files in docs/adr/.

Usage:
    python scripts/generate_adr_index.py              # preview (stdout)
    python scripts/generate_adr_index.py --write      # write docs/adr/.index.yaml
    python scripts/generate_adr_index.py --check      # check index is up-to-date (CI mode)

The generated index allows LLM agents to find relevant ADRs by keyword or
concern without reading all 170+ individual files.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import NamedTuple

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "adr"
INDEX_PATH = ADR_DIR / ".index.yaml"

# Concern keywords mapped to concern labels (order matters — first match wins)
CONCERN_RULES: list[tuple[str, list[str]]] = [
    ("bootstrap", ["bootstrap", "hetzner", "rescue", "installimage", "debian-packages"]),
    ("host-os", ["proxmox", "debian", "host-os", "target-os"]),
    ("vm-topology", ["vm", "topology", "guest", "provision", "cloud-init", "template"]),
    ("networking", ["network", "bridge", "nat", "ingress", "egress", "subdomain", "dns"]),
    ("security", ["security", "hardening", "firewall", "mtls", "credential", "secret", "token", "key", "certificate", "tls"]),
    ("storage", ["storage", "backup", "pbs", "volume", "disk"]),
    ("monitoring", ["monitoring", "grafana", "prometheus", "alertmanager", "metrics", "observability", "loki", "tempo"]),
    ("ci-cd", ["ci", "cd", "gitea", "github", "actions", "pipeline", "validation", "pre-push", "gate"]),
    ("automation", ["ansible", "playbook", "role", "windmill", "workflow", "automation", "scheduled"]),
    ("identity", ["keycloak", "sso", "oidc", "identity", "authentication", "authorization", "access"]),
    ("documentation", ["changelog", "runbook", "documentation", "portal", "search", "indexing"]),
    ("testing", ["testing", "test", "pytest", "molecule", "integration-test", "idempotency"]),
    ("release", ["release", "version", "changelog", "semantic"]),
    ("api", ["api", "gateway", "catalog", "openapi", "rest"]),
    ("agent-discovery", ["agent", "discovery", "index", "metadata", "handoff", "context"]),
    ("agent-coordination", ["coordination", "concurrency", "lock", "handoff", "parallelism", "deadlock"]),
    ("resilience", ["retry", "circuit-breaker", "timeout", "fault", "watchdog", "degradation"]),
    ("platform", ["platform", "manifest", "scaffold", "capability"]),
]

STATUS_KEYWORDS = {
    "Not Implemented": ["not implemented"],
    "Partial": ["partial", "partially implemented"],
    "Implemented": ["implemented", "live", "deployed"],
    "Accepted": ["accepted"],
    "Deprecated": ["deprecated", "superseded"],
    "Proposed": ["proposed"],
}


class AdrMeta(NamedTuple):
    number: str          # e.g. "0001"
    title: str
    status: str          # Accepted | Implemented | Proposed | Deprecated
    impl_status: str     # Implemented | Proposed | Accepted | Deprecated
    impl_version: str | None
    date: str
    concern: str
    keywords: list[str]
    summary: str
    filename: str        # relative path under docs/adr/


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _read_first_n_lines(path: Path, n: int = 30) -> str:
    with path.open(encoding="utf-8") as f:
        return "".join(f.readline() for _ in range(n))


def _extract_value(text: str, key: str, default: str = "") -> str:
    m = re.search(rf"^[-*]\s+{key}:\s+(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(rf"^#{1,2}\s+{key}:\s+(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return default


def _extract_title(text: str) -> str:
    m = re.search(r"^#\s+ADR\s+\d+[:\s]+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return "Unknown"


def _extract_status(text: str) -> tuple[str, str]:
    """Return (status, implementation_status)."""
    status = _extract_value(text, "Status", "Proposed")
    impl = _extract_value(text, "Implementation Status", status)
    status_lower = status.lower()
    impl_lower = impl.lower()
    # Normalise with longer and negated phrases first so "not implemented"
    # does not collapse into "Implemented".
    for normalised, variants in STATUS_KEYWORDS.items():
        if any(v in status_lower for v in variants):
            status = normalised
            break
    for normalised, variants in STATUS_KEYWORDS.items():
        if any(v in impl_lower for v in variants):
            impl = normalised
            break
    return status, impl


def _extract_date(text: str) -> str:
    m = re.search(r"^[-*]\s+Date:\s+(\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
    if m:
        return m.group(1)
    return "2026-03-21"


def _extract_impl_version(text: str) -> str | None:
    m = re.search(r"implemented.*?version.*?([\d]+\.[\d]+\.[\d]+)", text[:500], re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _infer_concern(title: str, keywords: list[str]) -> str:
    haystack = " ".join([title.lower()] + [k.lower() for k in keywords])
    for concern, rules in CONCERN_RULES:
        if any(r in haystack for r in rules):
            return concern
    return "platform"


def _extract_keywords(title: str, text: str) -> list[str]:
    """Derive keywords from title words (lowercased, de-duped)."""
    words = re.findall(r"[a-z][a-z0-9\-]+", title.lower())
    stopwords = {"for", "and", "the", "with", "via", "of", "to", "in", "on", "a", "an"}
    return [w for w in words if w not in stopwords][:8]


def _extract_summary(path: Path, title: str) -> str:
    """Read up to 80 lines, return first sentence from Decision section."""
    try:
        with path.open(encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return f"See {path.name}"

    in_decision = False
    for line in lines[:80]:
        if re.match(r"^#{1,3}\s+Decision", line, re.IGNORECASE):
            in_decision = True
            continue
        if in_decision:
            line = line.strip()
            if line and not line.startswith("#"):
                # Strip markdown formatting, truncate
                clean = re.sub(r"[*_`\[\]]", "", line)
                clean = re.sub(r"\(https?://[^\)]+\)", "", clean)
                return clean[:120]
    return title


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_adr(path: Path) -> AdrMeta | None:
    m = re.match(r"^(\d{4})", path.name)
    if not m:
        return None
    number = m.group(1)

    header = _read_first_n_lines(path, 30)
    title = _extract_title(header)
    status, impl_status = _extract_status(header)
    date = _extract_date(header)
    impl_version = _extract_impl_version(header)
    keywords = _extract_keywords(title, [])
    concern = _infer_concern(title, keywords)
    summary = _extract_summary(path, title)

    return AdrMeta(
        number=number,
        title=title,
        status=status,
        impl_status=impl_status,
        impl_version=impl_version,
        date=date,
        concern=concern,
        keywords=keywords,
        summary=summary,
        filename=path.name,
    )


# ---------------------------------------------------------------------------
# Concern registry builder
# ---------------------------------------------------------------------------

def build_concerns_registry(adrs: list[AdrMeta]) -> dict[str, list[str]]:
    registry: dict[str, list[str]] = {}
    for adr in adrs:
        registry.setdefault(adr.concern, []).append(adr.number)
    return dict(sorted(registry.items()))


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

def build_index(adrs: list[AdrMeta]) -> dict:
    counts: dict[str, int] = {}
    for adr in adrs:
        counts[adr.impl_status] = counts.get(adr.impl_status, 0) + 1

    entries = []
    for adr in adrs:
        entry: dict = {
            "adr": adr.number,
            "title": adr.title,
            "status": adr.status,
            "implementation_status": adr.impl_status,
            "date": adr.date,
            "concern": adr.concern,
            "keywords": adr.keywords,
            "summary": adr.summary,
            "filename": adr.filename,
        }
        if adr.impl_version:
            entry["implemented_version"] = adr.impl_version
        entries.append(entry)

    return {
        "schema_version": 1,
        "generated": datetime.date.today().isoformat(),
        "total_adrs": len(adrs),
        "implementation_status_summary": counts,
        "concerns": build_concerns_registry(adrs),
        "discovery_queries": {
            "how do we bootstrap": ["0001", "0003", "0004", "0005"],
            "authentication and identity": ["0007", "0056", "0147"],
            "ci and testing": ["0031", "0083", "0111", "0143"],
            "automation and workflows": ["0044", "0090"],
            "disaster recovery": ["0029", "0051"],
            "monitoring and observability": ["0011", "0027", "0032"],
            "networking and ingress": ["0012", "0013", "0014", "0015"],
            "vm management": ["0010", "0016", "0018"],
            "agent access and coordination": ["0007", "0090", "0131", "0132"],
            "multi-agent handoff": ["0163", "0164", "0165", "0166", "0167", "0168"],
            "deployment and release": ["0081", "0143"],
            "local services": ["0023", "0024", "0027", "0043", "0044"],
            "security hardening": ["0006", "0007", "0024", "0047", "0102"],
            "data and state": ["0033", "0037", "0038", "0132"],
        },
        "agent_discovery_tips": [
            "Search 'keywords' fields for terms relevant to your task",
            "Use 'concern' to find all ADRs in a domain",
            "Use 'discovery_queries' for common question patterns",
            "Check 'implementation_status' to skip Proposed decisions",
            "This file is generated — run 'python scripts/generate_adr_index.py --write' to refresh",
        ],
        "adr_index": entries,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate docs/adr/.index.yaml")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="Write index to docs/adr/.index.yaml")
    group.add_argument("--check", action="store_true", help="Exit 1 if index is stale (CI mode)")
    args = parser.parse_args(argv)

    # Collect and parse all ADR files
    adr_files = sorted(ADR_DIR.glob("0[0-9][0-9][0-9]-*.md"))
    adrs = [a for path in adr_files if (a := parse_adr(path)) is not None]

    index = build_index(adrs)

    if args.check:
        if not INDEX_PATH.exists():
            print(f"ERROR: {INDEX_PATH} does not exist. Run: python scripts/generate_adr_index.py --write")
            return 1
        with INDEX_PATH.open(encoding="utf-8") as f:
            existing = yaml.safe_load(f)
        # Compare total count
        if existing.get("total_adrs") != index["total_adrs"]:
            print(
                f"ERROR: docs/adr/.index.yaml is stale "
                f"(has {existing.get('total_adrs')} ADRs, found {index['total_adrs']}). "
                f"Run: python scripts/generate_adr_index.py --write"
            )
            return 1
        print(f"OK: docs/adr/.index.yaml is current ({index['total_adrs']} ADRs)")
        return 0

    # Serialise to YAML
    header = (
        "# ============================================================================\n"
        "# ADR Metadata Index — ADR 0164\n"
        "# ============================================================================\n"
        "# GENERATED FILE — do not edit by hand\n"
        "# Regenerate: python scripts/generate_adr_index.py --write\n"
        "# ============================================================================\n\n"
    )
    content = header + yaml.dump(index, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)

    if args.write:
        INDEX_PATH.write_text(content, encoding="utf-8")
        print(f"Written {INDEX_PATH} ({index['total_adrs']} ADRs indexed)")
    else:
        print(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
