#!/usr/bin/env python3

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Any

from adr_catalog import resolve_service_adr_path
from controller_automation_toolkit import emit_cli_error, repo_path
from deployment_history import DEFAULT_AUDIT_LOOKBACK_DAYS, load_deployment_history, load_service_catalog_data
from environment_catalog import configured_environment_ids
from ops_portal.contextual_help import build_changelog_page_help
from portal_utils import PORTAL_STYLES, escape, page_template, render_badge, render_external_link


BUILD_DIR = repo_path("build", "changelog-portal")
ENVIRONMENT_NAV = [
    (f"environment/{environment}/index.html", environment.replace("-", " ").title())
    for environment in configured_environment_ids()
]
NAV = [
    ("index.html", "Timeline"),
    ("services/index.html", "Services"),
    *ENVIRONMENT_NAV,
    ("promotions/index.html", "Promotions"),
]


def normalized_nav(current: str) -> list[tuple[str, str, bool]]:
    current_path = Path(current)
    items = []
    for href, label in NAV:
        target = Path(href)
        relative = Path(*([".."] * len(current_path.parent.parts) + list(target.parts)))
        if not current_path.parent.parts:
            relative = target
        items.append((str(relative), label, href == current))
    return items


def write_page(output_dir: Path, relative_path: str, title: str, subtitle: str, body: str) -> None:
    target = output_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    depth_prefix = "../" * len(Path(relative_path).parent.parts)
    target.write_text(
        page_template(
            title=title,
            subtitle=subtitle,
            nav_items=normalized_nav(relative_path),
            body=body,
            page_path=depth_prefix,
            contextual_help=build_changelog_page_help(relative_path),
        ),
        encoding="utf-8",
    )


def render_summary(history: dict[str, Any], service_catalog: dict[str, Any]) -> str:
    stats = history["stats"]
    services_touched = len({service_id for entry in history["entries"] for service_id in entry.get("service_ids", [])})
    metrics = [
        ("Timeline Entries", str(len(history["entries"]))),
        ("Live Applies", str(stats["live_apply_count"])),
        ("Promotions", str(stats["promotion_count"])),
        ("Audit Events", str(stats["mutation_audit_count"])),
        ("Services Touched", str(services_touched)),
        ("Catalog Services", str(len(service_catalog["services"]))),
    ]
    cards = []
    for label, value in metrics:
        cards.append(
            '<section class="panel metric">'
            f'<span class="metric-label">{escape(label)}</span>'
            f'<strong class="metric-value">{escape(value)}</strong>'
            "</section>"
        )
    return '<section class="summary-grid">' + "".join(cards) + "</section>"


def render_warning_banner(warnings: list[str]) -> str:
    if not warnings:
        return ""
    body = "".join(f"<p>{escape(item)}</p>" for item in warnings)
    return (
        '<section class="panel warning-banner">'
        f'<div class="card-head"><h2 class="section-title">Fallback Mode</h2>{render_badge("receipts-only", "warn")}</div>'
        f"{body}"
        "</section>"
    )


def render_entry_rows(entries: list[dict[str, Any]]) -> str:
    rows = []
    for entry in entries:
        tone = "ok" if entry["outcome"] == "success" else "warn" if entry["outcome"] == "partial" else "danger"
        type_tone = "neutral"
        if entry["change_type"] == "promotion":
            type_tone = "ok"
        elif entry["change_type"] in {"manual", "command-catalog"}:
            type_tone = "warn"
        services = ", ".join(entry.get("service_names") or entry.get("service_ids") or ["unclassified"])
        targets = ", ".join(entry.get("vm_names") or entry.get("targets") or ["n/a"])
        link = entry.get("link_path")
        if link:
            if link.startswith("http://") or link.startswith("https://"):
                source = render_external_link(link, "Source")
            else:
                source = render_external_link(str(repo_path(link)), "Source")
        else:
            source = "n/a"
        rows.append(
            "<tr>"
            f"<td>{escape(entry['date_label'])}</td>"
            f"<td>{render_badge(entry['change_type'], type_tone)}</td>"
            f'<td>{escape(entry["actor"])}<div class="muted">{escape(entry["actor_class"])}</div></td>'
            f"<td>{escape(services)}</td>"
            f"<td>{escape(targets)}</td>"
            f"<td>{render_badge(entry['outcome'], tone)}</td>"
            f"<td>{escape(entry['summary'])}</td>"
            f"<td>{source}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_timeline(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return '<section class="panel"><p>No history entries matched the current filter.</p></section>'
    return (
        '<section class="panel">'
        '<div class="table-scroll"><table>'
        "<thead><tr><th>Time</th><th>Type</th><th>Actor</th><th>Services</th><th>Targets</th><th>Outcome</th><th>Summary</th><th>Link</th></tr></thead>"
        f"<tbody>{render_entry_rows(entries)}</tbody></table></div></section>"
    )


def render_service_index(service_catalog: dict[str, Any], entries: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for entry in entries:
        for service_id in entry.get("service_ids", []):
            counts[service_id] = counts.get(service_id, 0) + 1

    cards = []
    for service in sorted(service_catalog["services"], key=lambda item: item["name"]):
        count = counts.get(service["id"], 0)
        cards.append(
            '<article class="card">'
            '<div class="card-head">'
            f'<div><h3>{escape(service["name"])}</h3><p class="muted">{escape(service["description"])}</p></div>'
            f"<div>{render_badge(service['lifecycle_status'], 'neutral')}{render_badge(f'{count} changes', 'ok' if count else 'neutral')}</div>"
            "</div>"
            '<div class="meta-list">'
            f"<div><strong>Service ID</strong><span>{escape(service['id'])}</span></div>"
            f"<div><strong>Primary URL</strong><span>{escape(service.get('public_url') or service.get('internal_url') or 'n/a')}</span></div>"
            "</div>"
            f'<div class="chip-row"><a class="chip-link" href="../service/{escape(service["id"])}/index.html">History</a></div>'
            "</article>"
        )
    return f'<section class="card-grid">{"".join(cards)}</section>'


def render_service_page(service: dict[str, Any], entries: list[dict[str, Any]]) -> str:
    links = []
    if service.get("runbook"):
        links.append(render_external_link(str(repo_path(service["runbook"])), "Runbook"))
    if service.get("public_url"):
        links.append(render_external_link(service["public_url"], "Public URL"))
    elif service.get("internal_url"):
        links.append(render_external_link(service["internal_url"], "Internal URL"))
    adr_path = resolve_service_adr_path(service)
    if adr_path is not None:
        links.append(render_external_link(str(adr_path), f"ADR {service['adr']}"))

    header = (
        '<section class="panel">'
        '<div class="card-head">'
        f'<div><h2>{escape(service["name"])}</h2><p class="muted">{escape(service["description"])}</p></div>'
        f"<div>{render_badge(service['lifecycle_status'], 'neutral')}{render_badge(service['exposure'], 'neutral')}</div>"
        "</div>"
        '<div class="meta-list">'
        f"<div><strong>Service ID</strong><span>{escape(service['id'])}</span></div>"
        f"<div><strong>VM</strong><span>{escape(service['vm'])}</span></div>"
        f"<div><strong>Primary URL</strong><span>{escape(service.get('public_url') or service.get('internal_url') or 'n/a')}</span></div>"
        "</div>" + (f'<div class="chip-row">{"".join(links)}</div>' if links else "") + "</section>"
    )
    return header + render_timeline(entries)


def render_promotions(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return '<section class="panel"><p>No promotion receipts are available yet.</p></section>'
    rows = []
    for entry in entries:
        metadata = entry.get("metadata", {})
        rows.append(
            "<tr>"
            f"<td>{escape(entry['date_label'])}</td>"
            f"<td>{escape(metadata.get('branch', 'unknown'))}</td>"
            f"<td>{escape(metadata.get('playbook', 'n/a'))}</td>"
            f"<td>{escape(entry['actor'])}</td>"
            f"<td>{escape(str(metadata.get('staging_validation_duration', 'n/a')))}</td>"
            f"<td>{escape(str(metadata.get('bypass_reason', 'none')))}</td>"
            f"<td>{render_external_link(str(repo_path(entry['link_path'])), 'Receipt')}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        '<div class="table-scroll"><table>'
        "<thead><tr><th>Date</th><th>Branch</th><th>Playbook</th><th>Actor</th><th>Validation Duration</th><th>Bypass</th><th>Receipt</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def validate_output(output_dir: Path, service_catalog: dict[str, Any]) -> None:
    expected = [
        output_dir / "index.html",
        output_dir / "services" / "index.html",
        output_dir / "environment" / "production" / "index.html",
        output_dir / "environment" / "staging" / "index.html",
        output_dir / "promotions" / "index.html",
        output_dir / "styles.css",
    ]
    expected.extend(output_dir / "service" / service["id"] / "index.html" for service in service_catalog["services"])
    for path in expected:
        if not path.exists():
            raise ValueError(f"missing generated portal artifact: {path}")


def render_portal(
    output_dir: Path,
    *,
    receipts_dir: Path = repo_path("receipts", "live-applies"),
    promotions_dir: Path = repo_path("receipts", "promotions"),
    mutation_audit_file: Path | None = None,
    loki_query_url: str | None = None,
    audit_lookback_days: int = DEFAULT_AUDIT_LOOKBACK_DAYS,
) -> None:
    service_catalog = load_service_catalog_data()
    history = load_deployment_history(
        receipts_dir=receipts_dir,
        promotions_dir=promotions_dir,
        service_catalog=service_catalog,
        mutation_audit_file=mutation_audit_file,
        loki_query_url=loki_query_url,
        audit_lookback_days=audit_lookback_days,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    styles = (
        PORTAL_STYLES
        + """
.warning-banner {
  border-color: rgba(155, 91, 22, 0.35);
  background: var(--warn-soft);
}
"""
    )
    (output_dir / "styles.css").write_text(styles, encoding="utf-8")

    warning_banner = render_warning_banner(history["warnings"])
    write_page(
        output_dir,
        "index.html",
        "Deployment History Portal",
        "Generated timeline of live applies, promotion receipts, and mutation audit events across the LV3 platform.",
        render_summary(history, service_catalog) + warning_banner + render_timeline(history["entries"]),
    )
    write_page(
        output_dir,
        "services/index.html",
        "Service Deployment History",
        "Per-service index of deployment history generated from receipts and audit evidence.",
        warning_banner + render_service_index(service_catalog, history["entries"]),
    )

    for service in service_catalog["services"]:
        service_entries = [item for item in history["entries"] if service["id"] in item.get("service_ids", [])]
        write_page(
            output_dir,
            f"service/{service['id']}/index.html",
            f"{service['name']} History",
            f"Deployment and mutation history for {service['name']}.",
            warning_banner + render_service_page(service, service_entries),
        )

    for environment in configured_environment_ids():
        environment_entries = [item for item in history["entries"] if item.get("environment") == environment]
        write_page(
            output_dir,
            f"environment/{environment}/index.html",
            f"{environment.title()} History",
            f"All recorded platform changes mapped to the {environment} environment.",
            warning_banner + render_timeline(environment_entries),
        )

    promotions = [item for item in history["entries"] if item["change_type"] == "promotion"]
    write_page(
        output_dir,
        "promotions/index.html",
        "Promotion Log",
        "Staging-to-production promotions and their gate evidence.",
        warning_banner + render_promotions(promotions),
    )

    validate_output(output_dir, service_catalog)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the static platform deployment history portal.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BUILD_DIR,
        help="Directory where the generated portal should be written.",
    )
    parser.add_argument(
        "--receipts-dir",
        type=Path,
        default=repo_path("receipts", "live-applies"),
        help="Root directory for live-apply receipts.",
    )
    parser.add_argument(
        "--promotions-dir",
        type=Path,
        default=repo_path("receipts", "promotions"),
        help="Root directory for promotion receipts.",
    )
    parser.add_argument(
        "--mutation-audit-file",
        type=Path,
        help="Optional JSONL file with mutation audit events for deterministic local generation.",
    )
    parser.add_argument("--loki-query-url", help="Override the Loki query_range URL for mutation audit events.")
    parser.add_argument(
        "--audit-lookback-days",
        type=int,
        default=DEFAULT_AUDIT_LOOKBACK_DAYS,
        help="How many days of mutation audit events to request from Loki.",
    )
    parser.add_argument("--write", action="store_true", help="Write output to the target directory.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Render into a temporary directory and verify expected portal outputs exist.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if not args.write and not args.check:
            parser.error("one of --write or --check is required")

        if args.check:
            with tempfile.TemporaryDirectory(prefix="changelog-portal-") as temp_dir:
                render_portal(
                    Path(temp_dir),
                    receipts_dir=args.receipts_dir,
                    promotions_dir=args.promotions_dir,
                    mutation_audit_file=args.mutation_audit_file,
                    loki_query_url=args.loki_query_url,
                    audit_lookback_days=args.audit_lookback_days,
                )
            return 0

        render_portal(
            args.output_dir,
            receipts_dir=args.receipts_dir,
            promotions_dir=args.promotions_dir,
            mutation_audit_file=args.mutation_audit_file,
            loki_query_url=args.loki_query_url,
            audit_lookback_days=args.audit_lookback_days,
        )
        return 0
    except Exception as exc:
        return emit_cli_error("changelog portal", exc)


if __name__ == "__main__":
    raise SystemExit(main())
