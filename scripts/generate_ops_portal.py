#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from adr_catalog import resolve_service_adr_path
from dependency_graph import dependency_summary, load_dependency_graph
from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from environment_topology import (
    load_environment_topology,
    validate_environment_references,
    validate_environment_topology,
)
from portal_utils import PORTAL_STYLES, escape, page_template, render_badge, render_external_link
from release_manager import build_release_status_snapshot
from service_catalog import load_service_catalog, validate_service_catalog
from slo_tracking import build_slo_status_entries
from subdomain_catalog import (
    load_public_edge_defaults,
    load_subdomain_catalog,
    validate_subdomain_catalog,
)
from agent_tool_registry import load_agent_tool_registry


STACK_PATH = repo_path("versions", "stack.yaml")
HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
ADR_DIR = repo_path("docs", "adr")
RUNBOOK_DIR = repo_path("docs", "runbooks")
BUILD_DIR = repo_path("build", "ops-portal")
SNAPSHOT_PATH = repo_path("receipts", "ops-portal-snapshot.html")
DRIFT_RECEIPTS_DIR = repo_path("receipts", "drift-reports")
FIXTURE_RECEIPTS_DIR = repo_path("receipts", "fixtures")
SECURITY_RECEIPTS_DIR = repo_path("receipts", "security-reports")
AGENT_COORDINATION_RECEIPTS_DIR = repo_path("receipts", "agent-coordination")

NAV = [
    ("index.html", "Service Map"),
    ("environments/index.html", "Environments"),
    ("vms/index.html", "VM Inventory"),
    ("subdomains/index.html", "DNS Map"),
    ("runbooks/index.html", "Runbook Index"),
    ("adrs/index.html", "ADR Log"),
    ("agents/index.html", "Agent Surface"),
]


@dataclass
class HealthState:
    status: str
    detail: str


def repo_link(path: str) -> str:
    return str(repo_path(path))


@lru_cache(maxsize=1)
def repo_remote_url() -> str:
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path(),
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""

    if remote.startswith("git@github.com:"):
        return "https://github.com/" + remote.removeprefix("git@github.com:").removesuffix(".git")
    if remote.startswith("https://github.com/"):
        return remote.removesuffix(".git")
    return ""


def repo_view_link(path: Path) -> str:
    remote = repo_remote_url()
    if remote.startswith("https://github.com/"):
        try:
            relative = path.relative_to(repo_path())
        except ValueError:
            return str(path)
        return f"{remote}/blob/main/{relative.as_posix()}"

    return str(path)


def parse_metadata_block(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.startswith("- "):
            if metadata:
                break
            continue
        key, _, value = line[2:].partition(":")
        if not value:
            continue
        metadata[key.strip()] = value.strip()
    return metadata


def read_h1(path: Path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def normalized_nav(current: str) -> list[tuple[str, str, bool]]:
    current_path = Path(current)
    items = []
    for href, label in NAV:
        target = Path(href)
        relative = Path(
            *(
                [".."] * len(current_path.parent.parts)
                + list(target.parts)
            )
        )
        if not current_path.parent.parts:
            relative = target
        items.append((str(relative), label, href == current))
    return items


def load_health_snapshot(path: Path | None) -> dict[str, HealthState]:
    if path is None:
        return {}
    payload = load_json(path)
    if isinstance(payload, dict) and "monitors" in payload:
        payload = payload["monitors"]

    states: dict[str, HealthState] = {}
    if isinstance(payload, dict):
        iterable = payload.items()
    else:
        iterable = []
        for item in payload:
            if isinstance(item, dict) and "name" in item:
                iterable.append((item["name"], item))

    for name, item in iterable:
        if isinstance(item, str):
            states[name] = HealthState(item, item)
            continue
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "unknown"))
        detail = str(item.get("detail") or item.get("message") or status)
        states[str(name)] = HealthState(status, detail)
    return states


def probe_url(url: str, timeout: float) -> HealthState:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        try:
            request = Request(url, method="HEAD")
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                code = response.getcode()
            if 200 <= code < 400:
                return HealthState("healthy", f"HTTP {code}")
            return HealthState("degraded", f"HTTP {code}")
        except Exception as exc:  # noqa: BLE001
            return HealthState("down", str(exc))
    if parsed.scheme in {"ssh", "postgres"}:
        host = parsed.hostname
        port = parsed.port or (22 if parsed.scheme == "ssh" else 5432)
        if not host:
            return HealthState("unknown", "no hostname")
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return HealthState("healthy", f"TCP {port}")
        except Exception as exc:  # noqa: BLE001
            return HealthState("down", str(exc))
    return HealthState("unknown", "no probe strategy")


def resolve_health(services: list[dict[str, Any]], snapshot: dict[str, HealthState], timeout: float) -> dict[str, HealthState]:
    resolved: dict[str, HealthState] = {}
    for service in services:
        if "uptime_monitor_name" in service and service["uptime_monitor_name"] in snapshot:
            resolved[service["id"]] = snapshot[service["uptime_monitor_name"]]
            continue
        if timeout <= 0:
            resolved[service["id"]] = HealthState("unknown", "probe skipped")
            continue
        probe_target = service.get("public_url") or service.get("internal_url")
        if not probe_target:
            resolved[service["id"]] = HealthState("unknown", "no URL")
            continue
        resolved[service["id"]] = probe_url(str(probe_target), timeout)
    return resolved


def badge_for_health(state: HealthState) -> str:
    mapping = {
        "healthy": ("healthy", "ok"),
        "up": ("healthy", "ok"),
        "configured": ("configured", "neutral"),
        "degraded": ("degraded", "warn"),
        "pending": ("pending", "warn"),
        "unknown": ("unknown", "neutral"),
        "down": ("down", "danger"),
    }
    label, tone = mapping.get(state.status, (state.status, "neutral"))
    return render_badge(label, tone)


def render_summary(
    services: list[dict[str, Any]],
    subdomains: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    environments: list[dict[str, Any]],
) -> str:
    metrics = [
        ("Services", str(len(services))),
        ("Environments", str(len(environments))),
        ("Public Subdomains", str(sum(1 for item in subdomains if item["status"] == "active"))),
        ("Private Surfaces", str(sum(1 for item in services if item["exposure"] == "private-only"))),
        ("Agent Tools", str(len(tools))),
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


def latest_drift_report() -> tuple[Path | None, dict[str, Any] | None]:
    reports = sorted(DRIFT_RECEIPTS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for report in reports:
        try:
            return report, load_json(report)
        except Exception:  # noqa: BLE001
            continue
    return None, None


def latest_security_report() -> tuple[Path | None, dict[str, Any] | None]:
    reports = sorted(
        SECURITY_RECEIPTS_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for report in reports:
        try:
            return report, load_json(report)
        except Exception:  # noqa: BLE001
            continue
    return None, None


def latest_agent_coordination_snapshot() -> tuple[Path | None, dict[str, Any] | None]:
    reports = sorted(
        AGENT_COORDINATION_RECEIPTS_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for report in reports:
        try:
            return report, load_json(report)
        except Exception:  # noqa: BLE001
            continue
    return None, None


def render_drift_panel() -> str:
    path, payload = latest_drift_report()
    if not path or not isinstance(payload, dict):
        return (
            '<section class="panel">'
            '<div class="card-head"><div><h2>Drift Status</h2><p class="muted">No drift receipt is committed yet.</p></div>'
            f"<div>{render_badge('unknown', 'neutral')}</div></div>"
            "</section>"
        )

    summary = payload.get("summary", {})
    status = str(summary.get("status", "unknown"))
    badge_tone = "ok" if status == "clean" else "warn" if status == "warn" else "danger"
    records = payload.get("records", [])
    top_rows = []
    for record in records[:5]:
        service = record.get("service") or record.get("resource") or "n/a"
        top_rows.append(
            "<tr>"
            f"<td>{escape(record.get('source', 'n/a'))}</td>"
            f"<td>{escape(service)}</td>"
            f"<td>{render_badge(str(record.get('severity', 'unknown')), 'warn' if record.get('severity') == 'warn' else 'danger' if record.get('severity') == 'critical' else 'neutral')}</td>"
            f"<td>{escape(record.get('detail', ''))}</td>"
            "</tr>"
        )
    receipt_link = render_external_link(repo_view_link(path), "Latest Receipt")
    generated_at = escape(str(payload.get("generated_at", "unknown")))
    status_metrics = (
        '<div class="meta-list">'
        f"<div><strong>Run</strong><span>{generated_at}</span></div>"
        f"<div><strong>Unsuppressed</strong><span>{escape(summary.get('unsuppressed_count', 0))}</span></div>"
        f"<div><strong>Warn</strong><span>{escape(summary.get('warn_count', 0))}</span></div>"
        f"<div><strong>Critical</strong><span>{escape(summary.get('critical_count', 0))}</span></div>"
        f"<div><strong>Suppressed</strong><span>{escape(summary.get('suppressed_count', 0))}</span></div>"
        "</div>"
    )
    empty_state_row = '<tr><td colspan="4">No actionable drift.</td></tr>'
    table = (
        '<div class="table-scroll"><table>'
        "<thead><tr><th>Source</th><th>Resource</th><th>Severity</th><th>Detail</th></tr></thead>"
        f"<tbody>{''.join(top_rows) if top_rows else empty_state_row}</tbody></table></div>"
    )
    return (
        '<section class="panel">'
        '<div class="card-head">'
        '<div><h2>Drift Status</h2><p class="muted">Latest multi-source drift report from the ADR 0091 receipt stream.</p></div>'
        f"<div>{render_badge(status, badge_tone)}</div>"
        "</div>"
        + status_metrics
        + f'<div class="chip-row">{receipt_link}</div>'
        + table
        + "</section>"
    )


def render_security_panel() -> str:
    path, payload = latest_security_report()
    if not path or not isinstance(payload, dict):
        return (
            '<section class="panel">'
            '<div class="card-head"><div><h2>Security Posture</h2><p class="muted">No security posture receipt is committed yet.</p></div>'
            f"<div>{render_badge('unknown', 'neutral')}</div></div>"
            "</section>"
        )

    summary = payload.get("summary", {})
    status = str(summary.get("status", "unknown"))
    badge_tone = "ok" if status == "clean" else "warn" if status == "warn" else "danger"
    hosts = payload.get("hosts", [])
    images = payload.get("images", [])
    top_rows = []
    for host in hosts[:5]:
        delta = host.get("hardening_index_delta")
        delta_text = "n/a" if delta is None else f"{delta:+d}"
        top_rows.append(
            "<tr>"
            f"<td>{escape(host.get('host', 'n/a'))}</td>"
            f"<td>{escape(host.get('hardening_index', 'n/a'))}</td>"
            f"<td>{escape(delta_text)}</td>"
            f"<td>{escape(host.get('new_findings_since_last_scan', 0))}</td>"
            "</tr>"
        )
    receipt_link = render_external_link(repo_view_link(path), "Latest Receipt")
    generated_at = escape(str(payload.get("generated_at", "unknown")))
    status_metrics = (
        '<div class="meta-list">'
        f"<div><strong>Run</strong><span>{generated_at}</span></div>"
        f"<div><strong>Critical CVEs</strong><span>{escape(summary.get('total_critical_cves', 0))}</span></div>"
        f"<div><strong>High CVEs</strong><span>{escape(summary.get('total_high_cves', 0))}</span></div>"
        f"<div><strong>Lowest Hardening</strong><span>{escape(summary.get('lowest_hardening_index', 'n/a'))}</span></div>"
        f"<div><strong>Scanned Images</strong><span>{escape(len(images))}</span></div>"
        "</div>"
    )
    empty_state_row = '<tr><td colspan="4">No host scan data.</td></tr>'
    table = (
        '<div class="table-scroll"><table>'
        "<thead><tr><th>Host</th><th>Index</th><th>Delta</th><th>New Findings</th></tr></thead>"
        f"<tbody>{''.join(top_rows) if top_rows else empty_state_row}</tbody></table></div>"
    )
    return (
        '<section class="panel">'
        '<div class="card-head">'
        '<div><h2>Security Posture</h2><p class="muted">Latest ADR 0102 receipt covering host hardening and runtime image CVEs.</p></div>'
        f"<div>{render_badge(status, badge_tone)}</div>"
        "</div>"
        + status_metrics
        + f'<div class="chip-row">{receipt_link}</div>'
        + table
        + "</section>"
    )


def render_release_panel() -> str:
    try:
        snapshot = build_release_status_snapshot(timeout=0.5)
    except Exception as exc:  # noqa: BLE001
        return (
            '<section class="panel">'
            '<div class="card-head"><div><h2>Release Readiness</h2><p class="muted">Unable to render release readiness.</p></div>'
            f"<div>{render_badge('unknown', 'neutral')}</div></div>"
            f'<p class="muted">{escape(str(exc))}</p>'
            "</section>"
        )

    summary = snapshot["summary"]
    blockers = snapshot["release_blockers"]
    badge = render_badge("ready" if summary["ready"] else "pending", "ok" if summary["ready"] else "warn")
    rows = []
    for criterion in snapshot["criteria"]:
        tone = "ok" if criterion["met"] else "warn"
        rows.append(
            "<tr>"
            f"<td>{escape(criterion['label'])}</td>"
            f"<td>{render_badge(criterion['status'], tone)}</td>"
            f"<td>{escape(criterion['detail'])}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        '<div class="card-head">'
        '<div><h2>Release Readiness</h2><p class="muted">Machine-checkable status for the ADR 0110 release policy and `1.0.0` target.</p></div>'
        f"<div>{badge}</div>"
        "</div>"
        '<div class="meta-list">'
        f"<div><strong>Repository</strong><span>{escape(snapshot['repo_version'])}</span></div>"
        f"<div><strong>Platform</strong><span>{escape(snapshot['platform_version'])}</span></div>"
        f"<div><strong>Blockers</strong><span>{escape(blockers['detail'])}</span></div>"
        f"<div><strong>Criteria</strong><span>{escape(summary['met'])}/{escape(summary['total'])} ({escape(summary['percent'])}%)</span></div>"
        "</div>"
        '<div class="table-scroll"><table>'
        "<thead><tr><th>Criterion</th><th>Status</th><th>Detail</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "</section>"
    )


def active_ephemeral_receipts() -> list[dict[str, Any]]:
    if not FIXTURE_RECEIPTS_DIR.exists():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(FIXTURE_RECEIPTS_DIR.glob("*.json")):
        if path.name.startswith("reaper-run-"):
            continue
        try:
            payload = load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("status") not in {"provisioning", "active"}:
            continue
        receipts.append(payload)
    return receipts


def render_ephemeral_vm_panel() -> str:
    receipts = active_ephemeral_receipts()
    if not receipts:
        return (
            '<section class="panel">'
            '<div class="card-head"><div><h2>Ephemeral VMs</h2><p class="muted">No active repo-managed ephemeral fixtures are recorded.</p></div>'
            f"<div>{render_badge('none', 'neutral')}</div></div>"
            "</section>"
        )

    rows = []
    for receipt in receipts:
        rows.append(
            "<tr>"
            f"<td>{escape(str(receipt.get('vm_id', 'n/a')))}</td>"
            f"<td>{escape(str(receipt.get('fixture_id', 'n/a')))}</td>"
            f"<td>{escape(str(receipt.get('owner', 'n/a')))}</td>"
            f"<td>{escape(str(receipt.get('purpose', 'n/a')))}</td>"
            f"<td>{escape(str(receipt.get('expires_at', 'n/a')))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        '<div class="card-head">'
        '<div><h2>Ephemeral VMs</h2><p class="muted">Repo-managed active ephemeral fixtures governed by ADR 0106.</p></div>'
        f"<div>{render_badge(str(len(receipts)), 'neutral')}</div>"
        "</div>"
        '<div class="table-scroll"><table>'
        "<thead><tr><th>VMID</th><th>Profile</th><th>Owner</th><th>Purpose</th><th>Expires</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        "</section>"
    )


def render_slo_panel(prometheus_url: str | None = None) -> str:
    entries = build_slo_status_entries(prometheus_url=prometheus_url)
    rows = []
    for entry in entries:
        budget = entry["metrics"]["budget_remaining"]
        compliance = entry["metrics"]["success_ratio_30d"]
        burn_rate = entry["metrics"]["burn_rate_1h"]
        exhaustion = entry["metrics"]["time_to_budget_exhaustion_days"]
        rows.append(
            "<tr>"
            f"<td>{escape(entry['id'])}</td>"
            f"<td>{escape(entry['service_id'])}</td>"
            f"<td>{render_badge(entry['status'], 'ok' if entry['status'] == 'healthy' else 'warn' if entry['status'] == 'warning' else 'danger' if entry['status'] == 'critical' else 'neutral')}</td>"
            f"<td>{escape(f'{compliance * 100:.2f}%' if compliance is not None else 'unknown')}</td>"
            f"<td>{escape(f'{budget * 100:.2f}%' if budget is not None else 'unknown')}</td>"
            f"<td>{escape(f'{burn_rate:.2f}x' if burn_rate is not None else 'unknown')}</td>"
            f"<td>{escape(f'{exhaustion:.1f}' if exhaustion is not None else 'unknown')}</td>"
            f"<td>{render_external_link(entry['dashboard_url'], 'Grafana')}</td>"
            "</tr>"
        )
    note = (
        '<p class="muted">Prometheus-backed SLO metrics are only shown when the generator can reach the monitoring API.</p>'
        if not prometheus_url
        else '<p class="muted">Current SLO budget state queried from Prometheus.</p>'
    )
    return (
        '<section class="panel">'
        '<div class="card-head">'
        '<div><h2>SLO Status</h2><p class="muted">Error budget posture for the ADR 0096 service-level objectives.</p></div>'
        f"<div>{render_badge(str(len(entries)), 'neutral')}</div>"
        "</div>"
        + note
        + '<div class="table-scroll"><table>'
        "<thead><tr><th>SLO</th><th>Service</th><th>Status</th><th>30d</th><th>Budget</th><th>Burn</th><th>Days Left</th><th>Dashboard</th></tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody></table></div>"
        + "</section>"
    )


def render_service_cards(
    services: list[dict[str, Any]],
    health: dict[str, HealthState],
    dependency_summaries: dict[str, dict[str, Any]],
) -> str:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    service_names = {service["id"]: service["name"] for service in services}
    for service in services:
        groups[service["category"]].append(service)

    blocks = []
    for category in sorted(groups):
        cards = []
        for service in sorted(groups[category], key=lambda item: item["name"]):
            state = health[service["id"]]
            chips = [
                render_badge(service["lifecycle_status"], "neutral"),
                render_badge(service["exposure"], "neutral"),
                badge_for_health(state),
            ]
            links = []
            if service.get("public_url"):
                links.append(render_external_link(service["public_url"], "UI"))
            elif service.get("internal_url"):
                links.append(render_external_link(service["internal_url"], "Access"))
            if service.get("runbook"):
                links.append(render_external_link(repo_view_link(repo_path(service["runbook"])), "Runbook"))
            if service.get("dashboard_url"):
                links.append(render_external_link(service["dashboard_url"], "Dashboard"))
            adr_path = resolve_service_adr_path(service)
            if adr_path is not None:
                links.append(render_external_link(repo_view_link(adr_path), f"ADR {service['adr']}"))

            summary = dependency_summaries[service["id"]]

            def names(service_ids: list[str]) -> str:
                return ", ".join(service_names.get(item, item) for item in service_ids)

            dependency_details = []
            if summary["depends_on"]["hard"]:
                dependency_details.append(
                    f"<div><strong>Hard deps</strong><span>{escape(names(summary['depends_on']['hard']))}</span></div>"
                )
            if summary["depends_on"]["soft"]:
                dependency_details.append(
                    f"<div><strong>Soft deps</strong><span>{escape(names(summary['depends_on']['soft']))}</span></div>"
                )
            if summary["depends_on"]["startup_only"]:
                dependency_details.append(
                    f"<div><strong>Startup deps</strong><span>{escape(names(summary['depends_on']['startup_only']))}</span></div>"
                )
            blast_radius = summary["impact"]["direct_hard"] + summary["impact"]["transitive_hard"]
            if blast_radius:
                dependency_details.append(
                    f"<div><strong>Failure blast radius</strong><span>{escape(names(blast_radius))}</span></div>"
                )

            tags = "".join(f'<span class="tag">{escape(tag)}</span>' for tag in service.get("tags", []))
            cards.append(
                '<article class="card">'
                '<div class="card-head">'
                f"<div><h3>{escape(service['name'])}</h3><p class=\"muted\">{escape(service['description'])}</p></div>"
                f"<div>{''.join(chips)}</div>"
                "</div>"
                '<div class="meta-list">'
                f"<div><strong>VM</strong><span>{escape(service['vm'])}"
                + (f" (VMID {escape(service['vmid'])})" if "vmid" in service else "")
                + "</span></div>"
                + f"<div><strong>Recovery tier</strong><span>{escape(str(summary['tier']))}</span></div>"
                + (f"<div><strong>Primary</strong><span>{escape(service.get('public_url') or service.get('internal_url') or 'n/a')}</span></div>")
                + f"<div><strong>Health</strong><span>{escape(state.detail)}</span></div>"
                + "</div>"
                + (f'<div class="meta-list">{"".join(dependency_details)}</div>' if dependency_details else "")
                + (f'<div class="chip-row">{tags}</div>' if tags else "")
                + (f'<div class="chip-row">{"".join(links)}</div>' if links else "")
                + "</article>"
            )
        blocks.append(
            '<section class="group-block panel">'
            f'<div class="group-header"><h2>{escape(category.title())}</h2><span class="muted">{len(groups[category])} services</span></div>'
            f'<div class="card-grid">{"".join(cards)}</div>'
            "</section>"
        )
    return "".join(blocks)


def render_environment_topology(
    environment_catalog: dict[str, Any],
    services: list[dict[str, Any]],
    subdomains: list[dict[str, Any]],
) -> str:
    environment_subdomains: dict[str, list[dict[str, Any]]] = defaultdict(list)
    environment_services: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)

    for entry in subdomains:
        environment_subdomains[entry["environment"]].append(entry)
    for service in services:
        for env_id, binding in service.get("environments", {}).items():
            environment_services[env_id].append((service, binding))

    blocks = []
    for environment in sorted(environment_catalog["environments"], key=lambda item: item["id"]):
        env_id = environment["id"]
        service_rows = []
        for service, binding in sorted(environment_services.get(env_id, []), key=lambda item: item[0]["name"]):
            service_rows.append(
                "<tr>"
                f"<td>{escape(service['name'])}</td>"
                f"<td>{render_badge(binding['status'], 'ok' if binding['status'] == 'active' else 'warn')}</td>"
                f"<td>{escape(binding['url'])}</td>"
                f"<td>{escape(binding.get('subdomain', 'n/a'))}</td>"
                "</tr>"
            )
        subdomain_rows = []
        for entry in sorted(environment_subdomains.get(env_id, []), key=lambda item: item["fqdn"]):
            subdomain_rows.append(
                "<tr>"
                f"<td>{escape(entry['fqdn'])}</td>"
                f"<td>{escape(entry.get('service_id', 'n/a'))}</td>"
                f"<td>{render_badge(entry['status'], 'ok' if entry['status'] == 'active' else 'warn')}</td>"
                f"<td>{escape(entry['exposure'])}</td>"
                "</tr>"
            )

        operator_access = (
            f"<div><strong>Operator Access</strong><span>{escape(environment['operator_access'])}</span></div>"
            if environment.get("operator_access")
            else ""
        )
        notes = (
            f"<div><strong>Notes</strong><span>{escape(environment['notes'])}</span></div>"
            if environment.get("notes")
            else ""
        )

        blocks.append(
            '<section class="group-block panel">'
            '<div class="card-head">'
            f"<div><h2>{escape(environment['name'])}</h2><p class=\"muted\">{escape(environment['purpose'])}</p></div>"
            f"<div>{render_badge(environment['status'], 'ok' if environment['status'] == 'active' else 'warn')}"
            f"{render_badge(environment['topology_model'], 'neutral')}</div>"
            "</div>"
            '<div class="meta-list">'
            f"<div><strong>Base Domain</strong><span>{escape(environment['base_domain'])}</span></div>"
            f"<div><strong>Pattern</strong><span>{escape(environment['hostname_pattern'])}</span></div>"
            f"<div><strong>Edge</strong><span>{escape(environment['edge_service_id'])} on {escape(environment['edge_vm'])}</span></div>"
            f"<div><strong>Ingress IPv4</strong><span>{escape(environment['ingress_ipv4'])}</span></div>"
            f"<div><strong>Isolation</strong><span>{escape(environment['isolation_model'])}</span></div>"
            f"{operator_access}"
            f"{notes}"
            "</div>"
            '<div class="table-scroll"><table>'
            "<thead><tr><th>Service</th><th>Status</th><th>URL</th><th>Subdomain</th></tr></thead>"
            f"<tbody>{''.join(service_rows)}</tbody></table></div>"
            '<div class="table-scroll"><table>'
            "<thead><tr><th>Subdomain</th><th>Service</th><th>Status</th><th>Exposure</th></tr></thead>"
            f"<tbody>{''.join(subdomain_rows)}</tbody></table></div>"
            "</section>"
        )

    return "".join(blocks)


def render_vm_inventory(
    services: list[dict[str, Any]],
    stack: dict[str, Any],
    guest_roles: dict[str, str],
) -> str:
    services_by_vm: dict[str, list[str]] = defaultdict(list)
    for service in services:
        services_by_vm[service["vm"]].append(service["name"])

    rows = []
    for guest in stack["observed_state"]["guests"]["instances"]:
        hosted = ", ".join(sorted(services_by_vm.get(guest["name"], []))) or "none"
        rows.append(
            "<tr>"
            f"<td>{escape(guest['vmid'])}</td>"
            f"<td>{escape(guest['name'])}</td>"
            f"<td>{escape(guest['ipv4'])}</td>"
            f"<td>{render_badge('running' if guest['running'] else 'stopped', 'ok' if guest['running'] else 'warn')}</td>"
            f"<td>{escape(guest_roles.get(guest['name'], 'unknown'))}</td>"
            f"<td>{escape(hosted)}</td>"
            "</tr>"
        )

    host_services = ", ".join(sorted(services_by_vm.get("proxmox_florin", []))) or "none"
    rows.insert(
        0,
        "<tr>"
        "<td>host</td>"
        "<td>proxmox_florin</td>"
        "<td>100.118.189.95</td>"
        f"<td>{render_badge('running', 'ok')}</td>"
        "<td>proxmox-host</td>"
        f"<td>{escape(host_services)}</td>"
        "</tr>",
    )

    return (
        '<section class="panel">'
        '<div class="table-scroll"><table>'
        "<thead><tr><th>ID</th><th>Name</th><th>IP</th><th>State</th><th>Role</th><th>Hosted Services</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def render_dns_map(subdomains: list[dict[str, Any]]) -> str:
    rows = []
    for entry in sorted(subdomains, key=lambda item: item["fqdn"]):
        tls = entry["tls"]["provider"]
        rows.append(
            "<tr>"
            f"<td>{escape(entry['fqdn'])}</td>"
            f"<td>{escape(entry['environment'])}</td>"
            f"<td>{escape(entry.get('service_id', 'n/a'))}</td>"
            f"<td>{render_badge(entry['status'], 'warn' if entry['status'] == 'planned' else 'ok' if entry['status'] == 'active' else 'neutral')}</td>"
            f"<td>{escape(entry['exposure'])}</td>"
            f"<td>{escape(entry['target'])}{':' + escape(entry['target_port']) if 'target_port' in entry else ''}</td>"
            f"<td>{escape(tls)}</td>"
            f"<td>{escape(entry.get('notes', ''))}</td>"
            "</tr>"
        )
    return (
        '<section class="panel">'
        '<div class="table-scroll"><table>'
        "<thead><tr><th>FQDN</th><th>Environment</th><th>Service</th><th>Status</th><th>Exposure</th><th>Target</th><th>TLS</th><th>Notes</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def render_runbooks() -> str:
    cards = []
    for path in sorted(RUNBOOK_DIR.glob("*.md")):
        title = read_h1(path)
        text = path.read_text()
        adr_match = sorted(set(re.findall(r"ADR\s+(\d{4})", text)))
        cards.append(
            '<article class="card">'
            f"<div class=\"row-head\"><h3>{escape(title)}</h3><span class=\"muted\">{escape(path.name)}</span></div>"
            f"<p class=\"muted\">Linked ADRs: {escape(', '.join(adr_match) if adr_match else 'none')}</p>"
            f'<div class="chip-row">{render_external_link(repo_view_link(path), "Open Markdown")}</div>'
            "</article>"
        )
    return (
        '<section class="panel toolbar">'
        '<input class="search-box" id="runbook-filter" placeholder="Filter runbooks by title or ADR">'
        '</section>'
        f'<section class="card-grid" id="runbook-grid">{"".join(cards)}</section>'
        '<script>'
        'const runbookFilter=document.getElementById("runbook-filter");'
        'const runbookCards=[...document.querySelectorAll("#runbook-grid .card")];'
        'runbookFilter?.addEventListener("input",()=>{const q=runbookFilter.value.toLowerCase();'
        'runbookCards.forEach(card=>{card.style.display=card.textContent.toLowerCase().includes(q)?"block":"none";});});'
        "</script>"
    )


def render_adrs() -> str:
    rows = []
    for path in sorted(ADR_DIR.glob("*.md")):
        metadata = parse_metadata_block(path)
        rows.append(
            "<tr>"
            f"<td>{escape(path.name.split('-', 1)[0])}</td>"
            f"<td>{escape(read_h1(path))}</td>"
            f"<td>{escape(metadata.get('Status', 'n/a'))}</td>"
            f"<td>{escape(metadata.get('Implementation Status', 'n/a'))}</td>"
            f"<td>{escape(metadata.get('Implemented In Repo Version', 'n/a'))}</td>"
            f"<td>{escape(metadata.get('Implemented In Platform Version', 'n/a'))}</td>"
            f"<td>{escape(metadata.get('Implemented On', 'n/a'))}</td>"
            f'<td>{render_external_link(repo_view_link(path), "Open")}</td>'
            "</tr>"
        )
    return (
        '<section class="panel">'
        '<div class="table-scroll"><table>'
        "<thead><tr><th>ADR</th><th>Title</th><th>Status</th><th>Implementation</th><th>Repo Version</th><th>Platform Version</th><th>Implemented On</th><th>Link</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def render_agents(tools: list[dict[str, Any]]) -> str:
    snapshot_path, snapshot_payload = latest_agent_coordination_snapshot()
    coordination_panel = ""
    if snapshot_path and isinstance(snapshot_payload, dict):
        summary = snapshot_payload.get("summary", {})
        entries = snapshot_payload.get("entries", [])
        rows = []
        if isinstance(entries, list):
            for item in entries[:8]:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    "<tr>"
                    f"<td>{escape(str(item.get('agent_id', 'unknown')))}</td>"
                    f"<td>{escape(str(item.get('current_phase', 'unknown')))}</td>"
                    f"<td>{escape(str(item.get('current_target') or 'n/a'))}</td>"
                    f"<td>{render_badge(str(item.get('status', 'unknown')), 'ok' if item.get('status') == 'active' else 'warn' if item.get('status') in {'blocked', 'escalated'} else 'neutral')}</td>"
                    f"<td>{escape(str(item.get('last_heartbeat', 'n/a')))}</td>"
                    "</tr>"
                )
        empty_coordination_row = '<tr><td colspan="5">No active sessions recorded.</td></tr>'
        coordination_panel = (
            '<section class="panel">'
            '<div class="card-head">'
            '<div><h2>Agent Coordination Map</h2><p class="muted">Latest recorded snapshot of active agent sessions.</p></div>'
            f"<div>{render_badge(str(summary.get('count', 0)), 'neutral')}</div>"
            "</div>"
            '<div class="meta-list">'
            f"<div><strong>Generated</strong><span>{escape(str(summary.get('generated_at', 'unknown')))}</span></div>"
            f"<div><strong>Active</strong><span>{escape(summary.get('active', 0))}</span></div>"
            f"<div><strong>Blocked</strong><span>{escape(summary.get('blocked', 0))}</span></div>"
            f"<div><strong>Escalated</strong><span>{escape(summary.get('escalated', 0))}</span></div>"
            "</div>"
            f'<div class="chip-row">{render_external_link(repo_view_link(snapshot_path), "Snapshot Receipt")}</div>'
            '<div class="table-scroll"><table>'
            "<thead><tr><th>Agent</th><th>Phase</th><th>Target</th><th>Status</th><th>Heartbeat</th></tr></thead>"
            f"<tbody>{''.join(rows) if rows else empty_coordination_row}</tbody></table></div>"
            "</section>"
        )
    else:
        coordination_panel = (
            '<section class="panel">'
            '<div class="card-head"><div><h2>Agent Coordination Map</h2><p class="muted">No coordination snapshot receipt is committed yet.</p></div>'
            f"<div>{render_badge('none', 'neutral')}</div></div>"
            "</section>"
        )

    cards = []
    for tool in sorted(tools, key=lambda item: (item["category"], item["name"])):
        cards.append(
            (
                '<article class="card">'
                '<div class="card-head">'
                f"<div><h3>{escape(tool['name'])}</h3><p class=\"muted\">{escape(tool['description'])}</p></div>"
                f"<div>{render_badge(tool['category'], 'neutral')}{render_badge(tool['transport'], 'neutral')}</div>"
                "</div>"
                '<div class="meta-list">'
                f"<div><strong>Endpoint</strong><span>{escape(tool['endpoint'])}</span></div>"
                f"<div><strong>Auth</strong><span>{escape(tool.get('auth', 'n/a'))}</span></div>"
                f"<div><strong>Approval</strong><span>{escape('required' if tool['approval_required'] else 'not required')}</span></div>"
                "</div>"
            )
            + (
                f'<div class="chip-row">{render_external_link(repo_view_link(repo_path(tool.get("owner_runbook") or tool["runbook"])), "Runbook")}</div>'
                if tool.get("owner_runbook") or tool.get("runbook")
                else ""
            )
            + "</article>"
        )
    return coordination_panel + f'<section class="card-grid">{"".join(cards)}</section>'


def load_agent_registry_best_effort() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return load_agent_tool_registry()
    except Exception:  # noqa: BLE001
        return (
            load_json(repo_path("config", "agent-tool-registry.json")),
            load_json(repo_path("config", "workflow-catalog.json")),
        )


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
        )
    )


def validate_output(output_dir: Path) -> None:
    expected = [
        output_dir / "index.html",
        output_dir / "environments" / "index.html",
        output_dir / "vms" / "index.html",
        output_dir / "subdomains" / "index.html",
        output_dir / "runbooks" / "index.html",
        output_dir / "adrs" / "index.html",
        output_dir / "agents" / "index.html",
        output_dir / "styles.css",
    ]
    for path in expected:
        if not path.exists():
            raise ValueError(f"missing generated portal artifact: {path}")


def render_portal(
    output_dir: Path,
    health_snapshot: Path | None,
    probe_timeout: float,
    snapshot_file: Path | None = None,
) -> None:
    environment_catalog = load_environment_topology()
    service_catalog = load_service_catalog()
    subdomain_catalog = load_subdomain_catalog()
    public_edge_defaults = load_public_edge_defaults()
    agent_registry, _workflow_catalog = load_agent_registry_best_effort()
    stack = load_yaml(STACK_PATH)
    host_vars = load_yaml(HOST_VARS_PATH)

    validate_environment_topology(environment_catalog, host_vars)
    validate_service_catalog(service_catalog)
    validate_subdomain_catalog(subdomain_catalog, service_catalog, host_vars, public_edge_defaults)
    validate_environment_references(environment_catalog, service_catalog, subdomain_catalog, host_vars)

    services = service_catalog["services"]
    environments = environment_catalog["environments"]
    subdomains = subdomain_catalog["subdomains"]
    tools = agent_registry["tools"]
    snapshot = load_health_snapshot(health_snapshot)
    health = resolve_health(services, snapshot, probe_timeout)
    slo_prometheus_url = os.environ.get("OPS_PORTAL_PROMETHEUS_URL", "")
    graph = load_dependency_graph(validate_schema=False)
    dependency_summaries = {
        service["id"]: dependency_summary(service["id"], graph)
        for service in services
    }
    guest_roles = {
        guest["name"]: guest["role"]
        for guest in host_vars["proxmox_guests"]
        if "name" in guest and "role" in guest
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "styles.css").write_text(PORTAL_STYLES)

    write_page(
        output_dir,
        "index.html",
        "Platform Operations Portal",
        "Generated operator map of services, health, and ownership across the current LV3 estate.",
        render_summary(services, subdomains, tools, environments)
        + render_slo_panel(slo_prometheus_url)
        + render_drift_panel()
        + render_security_panel()
        + render_release_panel()
        + render_ephemeral_vm_panel()
        + render_service_cards(services, health, dependency_summaries),
    )
    write_page(
        output_dir,
        "environments/index.html",
        "Environment Topology",
        "Canonical production and staging topology rendered from the environment, service, and subdomain catalogs.",
        render_environment_topology(environment_catalog, services, subdomains),
    )
    write_page(
        output_dir,
        "vms/index.html",
        "VM Inventory",
        "Observed VM inventory from versions/stack.yaml with hosted services stitched in from the service catalog.",
        render_vm_inventory(services, stack, guest_roles),
    )
    write_page(
        output_dir,
        "subdomains/index.html",
        "DNS Map",
        "Catalog of active and planned LV3 subdomains, targets, exposure, and certificate ownership.",
        render_dns_map(subdomains),
    )
    write_page(
        output_dir,
        "runbooks/index.html",
        "Runbook Index",
        "All operator runbooks in one place, with linked ADR references detected from the markdown source.",
        render_runbooks(),
    )
    write_page(
        output_dir,
        "adrs/index.html",
        "ADR Decision Log",
        "Repository ADRs with implementation metadata so operators can separate proposed contracts from real repo truth.",
        render_adrs(),
    )
    write_page(
        output_dir,
        "agents/index.html",
        "Agent Capability Surface",
        "Machine-readable tools currently available for agent and operator use, rendered for quick human inspection.",
        render_agents(tools),
    )
    validate_output(output_dir)
    if snapshot_file is not None:
        snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        snapshot_file.write_text((output_dir / "index.html").read_text())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the static platform operations portal.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BUILD_DIR,
        help="Directory where the generated portal should be written.",
    )
    parser.add_argument(
        "--health-snapshot",
        type=Path,
        help="Optional JSON snapshot mapping monitor names to statuses.",
    )
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=0.5,
        help="Timeout in seconds for direct service probes when no snapshot entry exists.",
    )
    parser.add_argument(
        "--snapshot-file",
        type=Path,
        default=SNAPSHOT_PATH,
        help="Optional single-file archive copy of the generated landing page.",
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
            with tempfile.TemporaryDirectory(prefix="ops-portal-") as temp_dir:
                render_portal(
                    Path(temp_dir),
                    args.health_snapshot,
                    0 if args.health_snapshot is None else args.probe_timeout,
                    None,
                )
            return 0

        render_portal(args.output_dir, args.health_snapshot, args.probe_timeout, args.snapshot_file)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("ops portal", exc)


if __name__ == "__main__":
    raise SystemExit(main())
