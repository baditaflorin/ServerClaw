#!/usr/bin/env python3
"""ADR 0443 Layer 1 — write-time topology linter.

Walks all non-allowlisted text files and flags any literal IP:port
that matches a known (host_group, internal_port) mapping derived from
`platform_service_registry` × `proxmox_guests`.

The intent is to catch templates and scripts that hardcode topology
facts which should instead be looked up from inventory at render time.

Allowlist (files that legitimately contain real IPs/ports):

    inventory/hosts.yml                — generated
    inventory/group_vars/platform.yml  — generated, real values
    inventory/host_vars/*.yml          — operator-authored topology source
    inventory/group_vars/all/*         — registry source
    catalog/**                         — per-service catalog (topology source)
    config/**                          — operator catalogs (workflow, api-gateway,
                                         slo, prometheus file_sd) — these consume
                                         the registry rather than re-emit it
    playbooks/vars/**                  — deployment overrides
    workstreams/**, workstreams.yaml   — workstream docs (often reference URLs)
    .local/**                          — per-deployment overrides (gitignored)
    docs/**, *.md                      — documentation, generic examples
    tests/**                           — test fixtures
    build/**                           — generated artifacts
    versions/**, receipts/**           — release receipts (historical evidence)

A single line may also opt out via the marker:

    ... 10.10.10.20:8093 ...  # noqa: topology-hardcode

Use sparingly, only when the literal is intentional (a doc-string example
or a default that the operator must override at runtime).

Detection rules:

  STRONG    `<ipv4>:<internal_port>` literal anywhere in a non-allowlisted
            file maps to exactly one service via the registry — flag it.

  HEURISTIC `<ipv4>` literal on a line that also mentions the matching
            service name (case-insensitive) — flag it. Reduces false
            positives compared to flagging every bare IP.

Both rules emit a precise `path:line:col  ip:port  service=<name>`
diagnostic. Exit code 0 when clean, 1 when any match is reported.

Usage:

    python3 scripts/validate_no_hardcoded_topology.py
    python3 scripts/validate_no_hardcoded_topology.py --json
    python3 scripts/validate_no_hardcoded_topology.py --root /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------

ALLOWLIST_DIRS: tuple[str, ...] = (
    ".git",
    ".claude",
    ".local",
    "build",
    "catalog",
    "config",
    "docs",
    "tests",
    "versions",
    "receipts",
    "workstreams",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
)

# Multi-segment path prefixes that should be allowlisted.
ALLOWLIST_PREFIXES: tuple[str, ...] = ("playbooks/vars/",)

ALLOWLIST_FILES: tuple[str, ...] = (
    "inventory/hosts.yml",
    "inventory/group_vars/platform.yml",
    "inventory/group_vars/platform_postgres.yml",
    "inventory/group_vars/platform_tls_certs.yml",
    "inventory/group_vars/postgres_guests.yml",
    "inventory/group_vars/lv3_guests.yml",
    "inventory/group_vars/backup_guests.yml",
    "inventory/group_vars/staging.yml",
    # Self — the linter source.
    "scripts/validate_no_hardcoded_topology.py",
    # Generators that legitimately bake real values.
    "scripts/generate_platform_vars.py",
    "scripts/generate_inventory.py",
    "scripts/generate_discovery_artifacts.py",
)

ALLOWLIST_GLOBS: tuple[str, ...] = (
    "inventory/host_vars/*.yml",
    "inventory/group_vars/all/**",
    "catalog/**",
    "config/**",
    "playbooks/vars/**",
    "workstreams/**",
    "workstreams.yaml",
    "*.md",
    "**/*.md",
    "RELEASE.md",
    "changelog.md",
)

# Per-line opt-out marker — leave the literal in place but suppress the
# finding. Use sparingly; the only legitimate case is a default URL in a
# script docstring or argparse default that the operator MUST override.
NOQA_MARKER = "noqa: topology-hardcode"

# Per-line opt-out for the LATE_BOUND_DEFAULT rule (ADR 0444 item 20).
# Format: `# late-bound-allow: <reason>`. The reason is required so a
# monthly audit can re-evaluate whether the allow is still warranted.
LATE_BOUND_ALLOW_MARKER = "late-bound-allow:"

# Glob patterns identifying role-default files. The LATE_BOUND_DEFAULT rule
# only fires on these — templates and tasks legitimately reference real
# topology at render time, but defaults must derive from platform_*.
LATE_BOUND_TARGET_GLOBS: tuple[str, ...] = (
    "roles/*/defaults/main.yml",
    "collections/ansible_collections/lv3/platform/roles/*/defaults/main.yml",
)

# File extensions we even bother reading.
TEXT_SUFFIXES: tuple[str, ...] = (
    ".yml",
    ".yaml",
    ".py",
    ".sh",
    ".bash",
    ".j2",
    ".tf",
    ".conf",
    ".cfg",
    ".ini",
    ".json",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".env",
    ".toml",
)


def _is_allowlisted(rel_path: Path) -> bool:
    parts = rel_path.parts
    if not parts:
        return False
    if parts[0] in ALLOWLIST_DIRS:
        return True
    posix = rel_path.as_posix()
    if posix in ALLOWLIST_FILES:
        return True
    for prefix in ALLOWLIST_PREFIXES:
        if posix.startswith(prefix):
            return True
    if posix == "workstreams.yaml":
        return True
    for pattern in ALLOWLIST_GLOBS:
        if rel_path.match(pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# Topology loading
# ---------------------------------------------------------------------------


def load_host_ip_map(repo_root: Path) -> dict[str, str]:
    """Return {host_group_name: ipv4} from inventory/host_vars/proxmox-host.yml."""
    path = repo_root / "inventory" / "host_vars" / "proxmox-host.yml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    guests = data.get("proxmox_guests") or []
    out: dict[str, str] = {}
    for g in guests:
        name = g.get("name")
        ipv4 = g.get("ipv4")
        if name and ipv4:
            out[str(name)] = str(ipv4)
    return out


def load_service_registry(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "inventory" / "group_vars" / "all" / "platform_services.yml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return data.get("platform_service_registry") or {}


@dataclass(frozen=True)
class ServiceMapping:
    name: str
    host_group: str
    ipv4: str
    port: int


def build_service_mappings(
    service_registry: dict[str, Any],
    host_ip_map: dict[str, str],
) -> list[ServiceMapping]:
    mappings: list[ServiceMapping] = []
    for name, entry in service_registry.items():
        if not isinstance(entry, dict):
            continue
        host = entry.get("host_group")
        port = entry.get("internal_port")
        if not host or port is None:
            continue
        ipv4 = host_ip_map.get(host)
        if not ipv4:
            continue
        try:
            port_int = int(port)
        except (TypeError, ValueError):
            continue
        mappings.append(
            ServiceMapping(
                name=name,
                host_group=host,
                ipv4=ipv4,
                port=port_int,
            )
        )
    return mappings


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    path: str
    line: int
    col: int
    rule: str  # "strong" | "heuristic"
    matched: str
    service: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "rule": self.rule,
            "matched": self.matched,
            "service": self.service,
            "detail": self.detail,
        }


def _iter_candidate_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if _is_allowlisted(rel):
            continue
        yield path


def scan_file(
    path: Path,
    rel: Path,
    mappings_by_ip_port: dict[tuple[str, int], ServiceMapping],
    mappings_by_ip: dict[str, list[ServiceMapping]],
) -> list[Finding]:
    """Scan a single file for hardcoded IP:port and bare-IP-near-name matches."""
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings

    # Build a regex matching only IPs we care about (anchor-free, exact match).
    candidate_ips = sorted({m.ipv4 for m in mappings_by_ip.values() for m in m})
    if not candidate_ips:
        return findings
    ip_alt = "|".join(re.escape(ip) for ip in candidate_ips)
    # Negative-look-around so 10.10.10.10 doesn't also match 10.10.10.100.
    ip_with_port_re = re.compile(rf"(?<![\d.])({ip_alt}):(\d{{1,5}})(?!\d)")
    bare_ip_re = re.compile(rf"(?<![\d.])({ip_alt})(?!\d)(?!\.\d)")

    for lineno, line in enumerate(text.splitlines(), start=1):
        if NOQA_MARKER in line:
            continue
        # STRONG: ip:port match
        for m in ip_with_port_re.finditer(line):
            ip = m.group(1)
            try:
                port = int(m.group(2))
            except ValueError:
                continue
            if port < 1 or port > 65535:
                continue
            key = (ip, port)
            svc = mappings_by_ip_port.get(key)
            if svc is None:
                continue
            findings.append(
                Finding(
                    path=rel.as_posix(),
                    line=lineno,
                    col=m.start() + 1,
                    rule="strong",
                    matched=f"{ip}:{port}",
                    service=svc.name,
                    detail=(
                        f"Literal {ip}:{port} maps to service '{svc.name}' "
                        f"on host_group '{svc.host_group}'. Derive from "
                        f"platform_service_registry instead."
                    ),
                )
            )

    # HEURISTIC: bare IP on a line that also mentions a service name.
    # Skip lines we already flagged (avoid duplicate noise).
    flagged_lines = {f.line for f in findings}
    for lineno, line in enumerate(text.splitlines(), start=1):
        if lineno in flagged_lines:
            continue
        if NOQA_MARKER in line:
            continue
        lower = line.lower()
        for m in bare_ip_re.finditer(line):
            ip = m.group(1)
            # Skip if this is part of an ip:port we'd have caught above
            tail = line[m.end() : m.end() + 6]
            if tail.startswith(":") and tail[1:2].isdigit():
                continue
            for svc in mappings_by_ip.get(ip, []):
                # Exact word-ish match on service name.
                if re.search(rf"\b{re.escape(svc.name)}\b", lower):
                    findings.append(
                        Finding(
                            path=rel.as_posix(),
                            line=lineno,
                            col=m.start() + 1,
                            rule="heuristic",
                            matched=ip,
                            service=svc.name,
                            detail=(
                                f"Bare IP {ip} appears near service name "
                                f"'{svc.name}'. host_group '{svc.host_group}' "
                                f"resolves to this IP — looks like a hardcoded "
                                f"topology reference."
                            ),
                        )
                    )
                    break  # one heuristic flag per IP occurrence

    return findings


def scan_late_bound_defaults(
    path: Path,
    rel: Path,
    known_ips: frozenset[str],
) -> list[Finding]:
    """ADR 0444 item 20 — flag `default('<known-prod-IP>')` in role defaults.

    The audit category from ADR 0438 ("openbao_postgres_host defaulting
    to a production IP before overlay applied") is the canonical case:
    a role default that bakes in a topology fact, so any deployment whose
    overlay loads after the default is read inherits the production IP
    silently.

    Only role-default files are scanned (LATE_BOUND_TARGET_GLOBS).
    Templates and task files legitimately reference real topology at
    render time; the issue is specifically defaults baked at parse time.

    Per-line opt-out: `# late-bound-allow: <reason>` on the same line.
    """
    if not any(rel.match(g) for g in LATE_BOUND_TARGET_GLOBS):
        return []
    if not known_ips:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    ip_alt = "|".join(re.escape(ip) for ip in sorted(known_ips))
    # Match Jinja `default('<ip>')` or `default("<ip>")`, with arbitrary
    # whitespace inside the parens. Anchored on the `default(` literal so
    # we don't match arbitrary string occurrences.
    default_re = re.compile(rf"\bdefault\(\s*['\"]({ip_alt})['\"]\s*\)")
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if LATE_BOUND_ALLOW_MARKER in line:
            continue
        if NOQA_MARKER in line:
            continue
        for m in default_re.finditer(line):
            ip = m.group(1)
            findings.append(
                Finding(
                    path=rel.as_posix(),
                    line=lineno,
                    col=m.start() + 1,
                    rule="late_bound_default",
                    matched=ip,
                    service="(role-default)",
                    detail=(
                        f"Role default uses default('{ip}') — the literal IP "
                        f"is read at parse time, before any deployment overlay "
                        f"can rebind it. Derive from platform_service_topology "
                        f"or a platform_* var instead. Annotate with "
                        f"`# late-bound-allow: <reason>` only if the literal "
                        f"is intentional and the operator MUST override."
                    ),
                )
            )
    return findings


def scan(
    repo_root: Path,
    *,
    extra_allowlist: tuple[str, ...] = (),
) -> list[Finding]:
    host_ip_map = load_host_ip_map(repo_root)
    registry = load_service_registry(repo_root)
    mappings = build_service_mappings(registry, host_ip_map)
    if not mappings:
        return []

    by_ip_port: dict[tuple[str, int], ServiceMapping] = {}
    by_ip: dict[str, list[ServiceMapping]] = {}
    for sm in mappings:
        by_ip_port[(sm.ipv4, sm.port)] = sm
        by_ip.setdefault(sm.ipv4, []).append(sm)
    known_ips = frozenset(host_ip_map.values())

    findings: list[Finding] = []
    for path in _iter_candidate_files(repo_root):
        rel = path.relative_to(repo_root)
        if any(rel.match(pat) for pat in extra_allowlist):
            continue
        findings.extend(scan_file(path, rel, by_ip_port, by_ip))
        findings.extend(scan_late_bound_defaults(path, rel, known_ips))
    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repo root to scan (default: this script's repo).")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON.")
    parser.add_argument(
        "--allow", action="append", default=[], help="Extra glob to skip (repeatable, relative to root)."
    )
    parser.add_argument(
        "--rule",
        choices=["all", "strong", "heuristic", "late_bound_default"],
        default="all",
        help="Restrict to a single rule (default: all).",
    )
    args = parser.parse_args(argv)

    findings = scan(Path(args.root), extra_allowlist=tuple(args.allow))
    if args.rule != "all":
        findings = [f for f in findings if f.rule == args.rule]

    if args.json:
        json.dump(
            {"finding_count": len(findings), "findings": [f.to_dict() for f in findings]},
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    else:
        if not findings:
            print("OK — no hardcoded topology references found.")
        else:
            print(f"Found {len(findings)} hardcoded topology reference(s):")
            for f in findings:
                print(f"  {f.path}:{f.line}:{f.col}  [{f.rule}]  {f.matched}  service={f.service}")
                print(f"     {f.detail}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
