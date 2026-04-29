#!/usr/bin/env python3
"""Generate one Markdown card per service — ADR 0473 phase 11.1.

Reads `catalog/services/<svc>/service.yaml` for every service and
writes `build/service-cards/<svc>.md`. Each card is a single-page
view of a service's identity, endpoints, health probes, owners and
ADR refs — the data an agent typically needs at the start of any
service-touching task.

The card is deterministic: re-running with no input change produces
byte-identical output, so `--check` is a freshness gate.

Outputs:
  build/service-cards/<svc>.md            one per service
  build/service-cards/index.md            link list

Exit:
  0  wrote (or `--check` passed)
  1  `--check` reported drift
  2  invocation error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = REPO_ROOT / "catalog" / "services"
OUTPUT_DIR = REPO_ROOT / "build" / "service-cards"


def discover_services(services_dir: Path = SERVICES_DIR) -> list[Path]:
    if not services_dir.is_dir():
        return []
    return sorted(p for p in services_dir.iterdir() if p.is_dir() and (p / "service.yaml").is_file())


def load_service(service_dir: Path) -> dict[str, Any]:
    payload = yaml.safe_load((service_dir / "service.yaml").read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{service_dir / 'service.yaml'}: top-level must be a mapping")
    return payload


def render_card(payload: dict[str, Any]) -> str:
    """Render one service card as Markdown. Pure function — fully
    deterministic given the same `payload`."""
    svc = payload.get("service") or {}
    if not isinstance(svc, dict):
        return f"# Malformed service entry\n\n{yaml.safe_dump(payload, sort_keys=True)}\n"

    name = svc.get("name") or svc.get("id") or "(unknown)"
    svc_id = svc.get("id") or "(unknown)"
    lines: list[str] = []
    lines.append(f"# {name} (`{svc_id}`)")
    lines.append("")
    if desc := svc.get("description"):
        lines.append(str(desc))
        lines.append("")

    lines.append("## Identity")
    lines.append("")
    for label, key in (
        ("Category", "category"),
        ("Lifecycle", "lifecycle_status"),
        ("VM", "vm"),
        ("VMID", "vmid"),
        ("Internal URL", "internal_url"),
        ("Public URL", "public_url"),
        ("Subdomain", "subdomain"),
        ("Exposure", "exposure"),
        ("Uptime monitor", "uptime_monitor_name"),
        ("Health probe", "health_probe_id"),
        ("ADR", "adr"),
    ):
        value = svc.get(key)
        if value not in (None, ""):
            lines.append(f"- **{label}:** {value}")
    lines.append("")

    if tags := svc.get("tags"):
        lines.append(f"**Tags:** {', '.join(str(t) for t in tags)}")
        lines.append("")

    envs = svc.get("environments") or {}
    if isinstance(envs, dict) and envs:
        lines.append("## Environments")
        lines.append("")
        lines.append("| Environment | Status | URL |")
        lines.append("|---|---|---|")
        for env_name in sorted(envs.keys()):
            entry = envs[env_name] or {}
            if not isinstance(entry, dict):
                continue
            status = entry.get("status", "?")
            url = entry.get("url", "")
            lines.append(f"| {env_name} | {status} | {url} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_index(services: list[tuple[str, str]]) -> str:
    """Render the index card listing every service."""
    lines = ["# Service cards", "", f"{len(services)} services indexed.", ""]
    for svc_id, name in services:
        lines.append(f"- [{name} (`{svc_id}`)]({svc_id}.md)")
    lines.append("")
    return "\n".join(lines)


def write_or_check(
    *,
    output_dir: Path,
    services_dir: Path,
    check: bool,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    discovered = discover_services(services_dir)
    rendered: dict[Path, str] = {}
    summary: list[tuple[str, str]] = []
    for service_dir in discovered:
        try:
            payload = load_service(service_dir)
        except (yaml.YAMLError, ValueError) as exc:
            print(f"generate_service_cards: skip {service_dir.name}: {exc}", file=sys.stderr)
            continue
        body = render_card(payload)
        rendered[output_dir / f"{service_dir.name}.md"] = body
        svc = payload.get("service") or {}
        if isinstance(svc, dict):
            summary.append((svc.get("id") or service_dir.name, svc.get("name") or svc.get("id") or service_dir.name))
    summary.sort()
    rendered[output_dir / "index.md"] = render_index(summary)

    drift: list[Path] = []
    for path, body in rendered.items():
        existing = path.read_text(encoding="utf-8") if path.is_file() else None
        if existing != body:
            if check:
                drift.append(path)
            else:
                path.write_text(body, encoding="utf-8")

    if check:
        if drift:
            for path in drift:
                print(f"generate_service_cards: stale {path.as_posix()}", file=sys.stderr)
            return 1
        return 0

    print(f"generate_service_cards: wrote {len(rendered)} files under {output_dir.as_posix()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--services-dir", default=str(SERVICES_DIR), help="Override the catalog/services dir.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Override the build/service-cards dir.")
    parser.add_argument("--check", action="store_true", help="Report drift instead of writing.")
    args = parser.parse_args(argv)
    return write_or_check(
        output_dir=Path(args.output_dir),
        services_dir=Path(args.services_dir),
        check=args.check,
    )


if __name__ == "__main__":
    sys.exit(main())
