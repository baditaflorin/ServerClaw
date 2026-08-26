#!/usr/bin/env python3
"""Multi-deployment service list and cross-deployment diff tool — ADR 0481.

Reads config/subdomain-exposure-registry.json (schema v3) and
config/deployment-registry.yaml to produce per-deployment service lists
and cross-deployment drift reports.

Usage:
  python3 scripts/list_services.py [OPTIONS]

Listing services for a single deployment:
  python3 scripts/list_services.py                           # primary (example.com)
  python3 scripts/list_services.py --deployment example.org    # fork
  python3 scripts/list_services.py --status active           # filter by status
  python3 scripts/list_services.py --format json             # JSON output
  python3 scripts/list_services.py --format csv              # CSV output

Cross-deployment diff:
  python3 scripts/list_services.py --diff example.com example.org  # compare two
  python3 scripts/list_services.py --diff example.com example.org --format json

List known deployments:
  python3 scripts/list_services.py --list-deployments

Exit codes:
  0  normal output (even if diff found differences)
  2  invocation error (unknown deployment, bad args)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "config" / "subdomain-exposure-registry.json"
DEPLOYMENT_REGISTRY_PATH = REPO_ROOT / "config" / "deployment-registry.yaml"

KNOWN_STATUSES = {"active", "planned", "retiring", "reserved"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceEntry:
    """Lightweight projection of a single publication, deployment-aware."""

    fqdn: str
    service_id: str
    status: str
    audience: str
    delivery_model: str
    access_model: str
    deployment: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeploymentMeta:
    slug: str
    platform_domain: str
    environment: str
    forked_from: str | None
    service_exclusions: frozenset[str]
    infrastructure_provider: str
    infrastructure_description: str


@dataclass
class DeploymentView:
    meta: DeploymentMeta
    services: list[ServiceEntry]

    @property
    def slug(self) -> str:
        return self.meta.slug

    def active(self) -> list[ServiceEntry]:
        return [s for s in self.services if s.status == "active"]


@dataclass
class DiffResult:
    left: DeploymentMeta
    right: DeploymentMeta
    only_left: list[ServiceEntry]  # in primary but excluded/absent on right
    only_right: list[ServiceEntry]  # on right but not in primary (future-proof)
    both: list[tuple[ServiceEntry, ServiceEntry]]  # (left_entry, right_entry)


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"registry not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"malformed registry JSON: {exc}") from exc


def _require_v3(registry: dict[str, Any]) -> None:
    v = registry.get("schema_version", "")
    if v != "3.0.0":
        raise SystemExit(
            f"registry schema_version is {v!r}; expected 3.0.0. "
            "Run: python3 scripts/subdomain_exposure_audit.py --write-registry"
        )


def _deployment_meta(slug: str, raw: dict[str, Any]) -> DeploymentMeta:
    infra = raw.get("infrastructure", {})
    return DeploymentMeta(
        slug=slug,
        platform_domain=raw.get("platform_domain", slug),
        environment=raw.get("environment", "production"),
        forked_from=raw.get("forked_from"),
        service_exclusions=frozenset(raw.get("service_exclusions", [])),
        infrastructure_provider=infra.get("provider", "unknown"),
        infrastructure_description=infra.get("description", ""),
    )


def list_deployments(registry: dict[str, Any]) -> list[DeploymentMeta]:
    """Return all known deployments in registry order (primary first)."""
    raw_deployments: dict[str, Any] = registry.get("deployments", {})
    primary = registry.get("primary_deployment", "example.com")
    metas: list[DeploymentMeta] = []
    # primary first, then others in insertion order
    for slug in sorted(raw_deployments, key=lambda s: (s != primary, s)):
        metas.append(_deployment_meta(slug, raw_deployments[slug]))
    return metas


# ---------------------------------------------------------------------------
# Service projection
# ---------------------------------------------------------------------------


def _entry_for_deployment(pub: dict[str, Any], deployment_domain: str, slug: str) -> ServiceEntry:
    """Project a primary publication entry onto a specific deployment domain."""
    original_fqdn: str = pub.get("fqdn", "")
    # Rewrite the domain suffix while preserving the subdomain label(s)
    primary_fqdn_parts = original_fqdn.rsplit(".", 2)  # [label, domain_apex1, domain_apex2] or fewer
    # Find the longest suffix that is a valid domain (not the subdomain label)
    # Strategy: replace everything after the first dot with the deployment domain,
    # unless the fqdn IS the apex (no dot-separated label).
    apex_primary = _infer_apex(original_fqdn)
    if apex_primary and original_fqdn != apex_primary:
        label = original_fqdn[: len(original_fqdn) - len(apex_primary) - 1]
        new_fqdn = f"{label}.{deployment_domain}"
    else:
        new_fqdn = deployment_domain

    return ServiceEntry(
        fqdn=new_fqdn,
        service_id=pub.get("service_id") or "",
        status=pub.get("status", ""),
        audience=pub.get("publication", {}).get("audience", ""),
        delivery_model=pub.get("publication", {}).get("delivery_model", ""),
        access_model=pub.get("publication", {}).get("access_model", ""),
        deployment=slug,
    )


def _infer_apex(fqdn: str) -> str:
    """Return the last two labels of an FQDN as the apex domain."""
    parts = fqdn.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return fqdn


def get_view(registry: dict[str, Any], slug: str) -> DeploymentView:
    """Build a DeploymentView for slug, deriving fork entries from the primary."""
    _require_v3(registry)
    raw_deployments: dict[str, Any] = registry.get("deployments", {})
    primary_slug = registry.get("primary_deployment", "example.com")

    if slug not in raw_deployments:
        known = ", ".join(sorted(raw_deployments))
        raise SystemExit(f"unknown deployment {slug!r}. Known: {known}")

    meta = _deployment_meta(slug, raw_deployments[slug])
    primary_pubs: list[dict[str, Any]] = registry.get("publications", [])

    if slug == primary_slug:
        services = [
            ServiceEntry(
                fqdn=p.get("fqdn", ""),
                service_id=p.get("service_id") or "",
                status=p.get("status", ""),
                audience=p.get("publication", {}).get("audience", ""),
                delivery_model=p.get("publication", {}).get("delivery_model", ""),
                access_model=p.get("publication", {}).get("access_model", ""),
                deployment=slug,
            )
            for p in primary_pubs
        ]
    else:
        # Derive: start with primary publications, apply exclusions, rewrite domain
        services = [
            _entry_for_deployment(p, meta.platform_domain, slug)
            for p in primary_pubs
            if (p.get("service_id") or "") not in meta.service_exclusions
        ]

    return DeploymentView(meta=meta, services=services)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _best_entry_by_service_id(services: list[ServiceEntry]) -> dict[str, ServiceEntry]:
    """Index services by service_id, preferring active/production over planned/staging.

    A service_id may appear multiple times when the same service has both a
    production and a staging publication. We want the production/active entry
    to represent the service in diff output so that "grafana" shows
    grafana.example.com (active) rather than grafana.staging.example.com (planned).
    """
    STATUS_RANK = {"active": 0, "planned": 1, "retiring": 2, "reserved": 3}
    ENV_RANK = {"production": 0, "staging": 1}

    result: dict[str, ServiceEntry] = {}
    for s in services:
        if not s.service_id:
            continue
        existing = result.get(s.service_id)
        if existing is None:
            result[s.service_id] = s
        else:
            # prefer lower-ranked (better) entry
            existing_rank = (
                STATUS_RANK.get(existing.status, 9),
                ENV_RANK.get("staging" if "staging" in existing.fqdn else "production", 0),
            )
            new_rank = (
                STATUS_RANK.get(s.status, 9),
                ENV_RANK.get("staging" if "staging" in s.fqdn else "production", 0),
            )
            if new_rank < existing_rank:
                result[s.service_id] = s
    return result


def diff_deployments(registry: dict[str, Any], left_slug: str, right_slug: str) -> DiffResult:
    """Compare two deployments by service_id."""
    left_view = get_view(registry, left_slug)
    right_view = get_view(registry, right_slug)

    left_by_id = _best_entry_by_service_id(left_view.services)
    right_by_id = _best_entry_by_service_id(right_view.services)

    all_ids = sorted(set(left_by_id) | set(right_by_id))
    only_left: list[ServiceEntry] = []
    only_right: list[ServiceEntry] = []
    both: list[tuple[ServiceEntry, ServiceEntry]] = []

    for sid in all_ids:
        in_left = sid in left_by_id
        in_right = sid in right_by_id
        if in_left and in_right:
            both.append((left_by_id[sid], right_by_id[sid]))
        elif in_left:
            only_left.append(left_by_id[sid])
        else:
            only_right.append(right_by_id[sid])

    return DiffResult(
        left=left_view.meta,
        right=right_view.meta,
        only_left=only_left,
        only_right=only_right,
        both=both,
    )


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def _filter_by_status(services: list[ServiceEntry], status: str | None) -> list[ServiceEntry]:
    if status is None or status == "all":
        return services
    return [s for s in services if s.status == status]


def _fmt_table(services: list[ServiceEntry], deployment: str) -> str:
    if not services:
        return f"{deployment} — no services (after filter)\n"
    col_fqdn = max(len(s.fqdn) for s in services)
    col_svc = max((len(s.service_id) for s in services), default=7)
    col_aud = max((len(s.audience) for s in services), default=8)
    header = f"{'FQDN':<{col_fqdn}}  {'SERVICE':<{col_svc}}  {'AUDIENCE':<{col_aud}}  STATUS"
    sep = "-" * len(header)
    lines = [header, sep]
    for s in sorted(services, key=lambda x: x.fqdn):
        lines.append(f"{s.fqdn:<{col_fqdn}}  {s.service_id:<{col_svc}}  {s.audience:<{col_aud}}  {s.status}")
    return "\n".join(lines)


def format_list(view: DeploymentView, *, status: str | None, fmt: str) -> str:
    services = _filter_by_status(view.services, status)
    meta = view.meta
    header_parts = [
        f"{meta.slug} — {len(services)} service(s)",
        f"  provider: {meta.infrastructure_provider} ({meta.infrastructure_description})",
    ]
    if meta.forked_from:
        excl = sorted(meta.service_exclusions)
        header_parts.append(f"  forked from: {meta.forked_from} | exclusions: {excl if excl else 'none'}")

    if fmt == "table":
        return "\n".join(header_parts) + "\n\n" + _fmt_table(services, meta.slug)

    if fmt == "json":
        payload = {
            "deployment": meta.slug,
            "platform_domain": meta.platform_domain,
            "environment": meta.environment,
            "forked_from": meta.forked_from,
            "service_exclusions": sorted(meta.service_exclusions),
            "total": len(services),
            "services": [s.to_dict() for s in sorted(services, key=lambda x: x.fqdn)],
        }
        return json.dumps(payload, indent=2)

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=["fqdn", "service_id", "status", "audience", "delivery_model", "access_model", "deployment"],
        )
        writer.writeheader()
        for s in sorted(services, key=lambda x: x.fqdn):
            writer.writerow(s.to_dict())
        return buf.getvalue().rstrip("\n")

    raise ValueError(f"unknown format: {fmt!r}")


def format_diff(diff: DiffResult, *, status: str | None, fmt: str) -> str:
    left_slug = diff.left.slug
    right_slug = diff.right.slug

    if fmt == "json":
        payload = {
            "left": left_slug,
            "right": right_slug,
            "summary": {
                "only_left": len(diff.only_left),
                "only_right": len(diff.only_right),
                "on_both": len(diff.both),
            },
            "only_left": [s.to_dict() for s in diff.only_left],
            "only_right": [s.to_dict() for s in diff.only_right],
            "on_both": [{"left": l.to_dict(), "right": r.to_dict()} for l, r in diff.both],
        }
        return json.dumps(payload, indent=2)

    lines: list[str] = [
        f"Cross-deployment diff: {left_slug} ↔ {right_slug}",
        "",
    ]

    if diff.only_left:
        lines.append(f"[only on {left_slug} — excluded from {right_slug}]  ({len(diff.only_left)})")
        excl = sorted(diff.right.service_exclusions)
        if excl:
            lines.append(f"  (exclusions declared in deployment-registry.yaml: {excl})")
        for s in sorted(diff.only_left, key=lambda x: x.service_id):
            lines.append(f"  {s.fqdn:<45}  {s.service_id:<25}  {s.audience}/{s.status}")
        lines.append("")

    if diff.only_right:
        lines.append(f"[only on {right_slug} — not in {left_slug}]  ({len(diff.only_right)})")
        for s in sorted(diff.only_right, key=lambda x: x.service_id):
            lines.append(f"  {s.fqdn:<45}  {s.service_id:<25}  {s.audience}/{s.status}")
        lines.append("")

    # Filter both by status if requested
    both_filtered = diff.both
    if status and status != "all":
        both_filtered = [(l, r) for l, r in diff.both if l.status == status or r.status == status]

    lines.append(f"[on both deployments]  ({len(both_filtered)})")
    for left_s, right_s in sorted(both_filtered, key=lambda p: p[0].service_id):
        status_note = ""
        if left_s.status != right_s.status:
            status_note = f"  ← status differs: {left_slug}={left_s.status} {right_slug}={right_s.status}"
        lines.append(f"  {left_s.service_id:<25}  {left_s.fqdn} ↔ {right_s.fqdn}{status_note}")

    lines.append("")
    lines.append(
        f"summary: {len(diff.only_left)} only on {left_slug} / "
        f"{len(diff.only_right)} only on {right_slug} / "
        f"{len(diff.both)} on both"
    )
    return "\n".join(lines)


def format_list_deployments(registry: dict[str, Any], *, fmt: str) -> str:
    metas = list_deployments(registry)
    primary_slug = registry.get("primary_deployment", "")

    if fmt == "json":
        return json.dumps(
            [
                {
                    "slug": m.slug,
                    "platform_domain": m.platform_domain,
                    "environment": m.environment,
                    "primary": m.slug == primary_slug,
                    "forked_from": m.forked_from,
                    "provider": m.infrastructure_provider,
                    "service_exclusions": sorted(m.service_exclusions),
                }
                for m in metas
            ],
            indent=2,
        )

    lines = [f"Known deployments ({len(metas)}):"]
    for m in metas:
        tag = " [primary]" if m.slug == primary_slug else f" [fork of {m.forked_from}]"
        excl = f" exclusions={sorted(m.service_exclusions)}" if m.service_exclusions else ""
        lines.append(f"  {m.slug:<20}{tag}  {m.infrastructure_provider}/{m.environment}{excl}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--list-deployments",
        action="store_true",
        help="Print all known deployments from config/deployment-registry.yaml.",
    )
    mode.add_argument(
        "--diff",
        nargs=2,
        metavar=("LEFT", "RIGHT"),
        help="Show what differs between two deployments (e.g. --diff example.com example.org).",
    )
    parser.add_argument(
        "--deployment",
        metavar="DOMAIN",
        help="Deployment to list services for (default: primary deployment).",
    )
    parser.add_argument(
        "--status",
        choices=["active", "planned", "retiring", "reserved", "all"],
        default=None,
        help="Filter by service status (default: show all statuses).",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        dest="fmt",
        help="Output format (default: table).",
    )
    parser.add_argument(
        "--registry",
        metavar="PATH",
        default=str(REGISTRY_PATH),
        help=f"Override the registry path (default: {REGISTRY_PATH}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_registry(Path(args.registry))

    if args.list_deployments:
        print(format_list_deployments(registry, fmt=args.fmt))
        return 0

    if args.diff:
        left_slug, right_slug = args.diff
        try:
            diff = diff_deployments(registry, left_slug, right_slug)
        except SystemExit as exc:
            print(f"list_services: {exc}", file=sys.stderr)
            return 2
        print(format_diff(diff, status=args.status, fmt=args.fmt))
        return 0

    # Default: list a single deployment
    slug = args.deployment or registry.get("primary_deployment", "example.com")
    try:
        view = get_view(registry, slug)
    except SystemExit as exc:
        print(f"list_services: {exc}", file=sys.stderr)
        return 2
    print(format_list(view, status=args.status, fmt=args.fmt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
