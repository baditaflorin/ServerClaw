#!/usr/bin/env python3
"""Host-pinning check — ADR 0457.

Verifies that no `proxmox_guests[*].deployment_owner` field is set to a
deployment slug other than the active one. The class of bug this catches
is the lv3 ↔ 0fork `oauth2-proxy@4180` collision: two different
deployments installed parallel systemd units on the same VM and the one
that started first won the port. Operationally manageable via manual
disable, but invisible at IaC level.

This script is a primitive: it reads the data and reports drift. Wiring
into specific role tasks (so a converge refuses to install on a host
owned by another deployment) is a follow-up workstream — that part has
wider blast radius and should land per-role with role-author review.

Invocations:

    # Validate the active deployment's topology against itself.
    python3 scripts/host_pinning_check.py

    # Validate a specific deployment by slug.
    python3 scripts/host_pinning_check.py --deployment 0fork

    # Validate that a specific host is owned by the active deployment.
    python3 scripts/host_pinning_check.py --host nginx

    # Cross-deployment drift mode: list every guest where deployment_owner
    # differs from the deployment whose topology declared it.
    python3 scripts/host_pinning_check.py --all

Exit codes:
    0 — no drift detected
    1 — drift detected (one or more guests have deployment_owner mismatched
        against the deployment they're declared in)
    2 — usage / data error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENTS_DIR = REPO_ROOT / ".local" / "deployments"


@dataclass
class HostPinningIssue:
    deployment: str
    guest_name: str
    declared_owner: str
    severity: str
    detail: str

    def as_dict(self) -> dict:
        return {
            "deployment": self.deployment,
            "guest": self.guest_name,
            "declared_owner": self.declared_owner,
            "severity": self.severity,
            "detail": self.detail,
        }


def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        print(
            "host_pinning_check: PyYAML missing — install pyyaml (uv run --with pyyaml) to use this script.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not path.is_file():
        return {}
    with path.open() as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _list_deployment_slugs() -> list[str]:
    if not DEPLOYMENTS_DIR.is_dir():
        return []
    return sorted(p.name for p in DEPLOYMENTS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))


def _resolve_active_slug(explicit: str | None) -> str | None:
    """Mirror scripts/deployment.py precedence (lite version — no subprocess)."""
    import os

    if explicit:
        return explicit.strip() or None
    env_slug = os.environ.get("DEPLOYMENT", "").strip()
    if env_slug:
        return env_slug
    active_file = REPO_ROOT / ".local" / "active-deployment"
    if active_file.is_file():
        slug = active_file.read_text().strip()
        if slug:
            return slug
    return None


def _audit_topology(slug: str, host_filter: str | None = None) -> list[HostPinningIssue]:
    """Return issues for one deployment's topology.

    A guest with no `deployment_owner` is a shared/legacy VM and is
    silently allowed — the field is opt-in, not mandatory. A guest
    with `deployment_owner: <other-slug>` declared inside this
    deployment's topology is the drift signal.
    """
    topology = _load_yaml(DEPLOYMENTS_DIR / slug / "topology.yml")
    guests = topology.get("proxmox_guests") or []
    if not isinstance(guests, list):
        return []

    issues: list[HostPinningIssue] = []
    for guest in guests:
        if not isinstance(guest, dict):
            continue
        name = guest.get("name", "")
        if host_filter and name != host_filter:
            continue
        owner = guest.get("deployment_owner")
        if not owner:
            continue
        if owner != slug:
            issues.append(
                HostPinningIssue(
                    deployment=slug,
                    guest_name=str(name),
                    declared_owner=str(owner),
                    severity="error",
                    detail=(
                        f"deployment_owner={owner!r} on guest {name!r} but the topology declaring it "
                        f"belongs to deployment {slug!r}. Either move this guest's stanza to the right "
                        f"deployment's topology.yml or correct the deployment_owner field."
                    ),
                )
            )
    return issues


def _audit_cross_deployment(active_slug: str) -> list[HostPinningIssue]:
    """Cross-deployment audit: when other deployments declare guests
    with `deployment_owner: <active-slug>`, surface them as informational
    cross-references. They are not errors — they're how a multi-deployment
    operator confirms that a VM is exclusively pinned to one deployment.

    A guest with a `deployment_owner` value that does NOT match the
    deployment whose topology declared it (across any deployment) is the
    real error, already covered by `_audit_topology` per-deployment.
    """
    issues: list[HostPinningIssue] = []
    for slug in _list_deployment_slugs():
        if slug == active_slug:
            continue
        topology = _load_yaml(DEPLOYMENTS_DIR / slug / "topology.yml")
        guests = topology.get("proxmox_guests") or []
        if not isinstance(guests, list):
            continue
        for guest in guests:
            if not isinstance(guest, dict):
                continue
            owner = guest.get("deployment_owner")
            if owner == active_slug:
                issues.append(
                    HostPinningIssue(
                        deployment=slug,
                        guest_name=str(guest.get("name", "")),
                        declared_owner=str(owner),
                        severity="info",
                        detail=(
                            f"guest {guest.get('name')!r} pinned to {active_slug!r} but its stanza "
                            f"lives in {slug!r}'s topology.yml — this is fine, it just confirms "
                            f"cross-deployment awareness of the pinning."
                        ),
                    )
                )
    return issues


def _audit_all() -> list[HostPinningIssue]:
    issues: list[HostPinningIssue] = []
    for slug in _list_deployment_slugs():
        issues.extend(_audit_topology(slug))
    return issues


def _print_human(issues: list[HostPinningIssue]) -> None:
    if not issues:
        print("host_pinning_check: no drift detected.")
        return
    by_severity = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        marker = {"error": "[!]", "warning": "[?]", "info": "[i]"}.get(issue.severity, "[?]")
        print(f"{marker} {issue.deployment}.{issue.guest_name}: {issue.detail}")
    summary = ", ".join(f"{k}={v}" for k, v in by_severity.items() if v > 0)
    print(f"\nhost_pinning_check: {len(issues)} issue(s) ({summary}).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="host_pinning_check",
        description="Verify proxmox_guests[*].deployment_owner pinning across deployments — ADR 0457.",
    )
    parser.add_argument(
        "--deployment",
        help="Deployment slug to audit (default: active deployment). Ignored when --all is set.",
    )
    parser.add_argument("--host", help="Restrict audit to a single guest name.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Audit every deployment under .local/deployments/ instead of just the active one.",
    )
    parser.add_argument(
        "--cross",
        action="store_true",
        help="Also surface informational cross-deployment pinning references for the active slug.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_out",
        help="Emit results as JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat info-level findings as errors too (exit non-zero).",
    )
    args = parser.parse_args(argv)

    if args.all:
        issues = _audit_all()
    else:
        slug = _resolve_active_slug(args.deployment)
        if not slug:
            print(
                "host_pinning_check: no active deployment resolved. Pass --deployment <slug>, "
                "set $DEPLOYMENT, or write .local/active-deployment.",
                file=sys.stderr,
            )
            return 2
        issues = _audit_topology(slug, host_filter=args.host)
        if args.cross:
            issues.extend(_audit_cross_deployment(slug))

    if args.json_out:
        print(json.dumps([i.as_dict() for i in issues], indent=2))
    else:
        _print_human(issues)

    severities = {i.severity for i in issues}
    if "error" in severities or (args.strict and severities):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
