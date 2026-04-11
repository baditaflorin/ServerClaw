#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, write_json


HEALTH_PROBE_CATALOG_PATH = repo_path("config", "health-probe-catalog.json")
UPTIME_MONITORS_PATH = repo_path("config", "uptime-kuma", "monitors.json")


def load_health_probe_catalog(path: Path = HEALTH_PROBE_CATALOG_PATH) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    services = payload.get("services")
    if not isinstance(services, dict):
        raise ValueError(f"{path} must define a services object")
    return payload


def build_uptime_monitors(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    services = catalog.get("services", {})
    monitors: list[dict[str, Any]] = []
    names: set[str] = set()

    for service_id, service in services.items():
        if not isinstance(service, dict):
            raise ValueError(f"health probe contract for '{service_id}' must be an object")
        uptime_kuma = service.get("uptime_kuma")
        if not isinstance(uptime_kuma, dict):
            raise ValueError(f"health probe contract for '{service_id}' must define uptime_kuma")
        if not uptime_kuma.get("enabled"):
            continue
        monitor = uptime_kuma.get("monitor")
        if not isinstance(monitor, dict):
            raise ValueError(f"health probe contract for '{service_id}' must define uptime_kuma.monitor")
        name = monitor.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"health probe contract for '{service_id}' must define uptime_kuma.monitor.name")
        if name in names:
            raise ValueError(f"duplicate Uptime Kuma monitor name in health probe catalog: {name}")
        names.add(name)
        monitors.append(monitor)

    if not monitors:
        raise ValueError("health probe catalog does not define any enabled Uptime Kuma monitors")
    return monitors


def render_uptime_monitors(monitors: list[dict[str, Any]]) -> str:
    return json.dumps(monitors, indent=2) + "\n"


def outputs_match(*, output_path: Path = UPTIME_MONITORS_PATH, catalog_path: Path = HEALTH_PROBE_CATALOG_PATH) -> bool:
    catalog = load_health_probe_catalog(catalog_path)
    expected = render_uptime_monitors(build_uptime_monitors(catalog))
    if not output_path.exists():
        return False
    return output_path.read_text(encoding="utf-8") == expected


def write_uptime_monitors(
    *, output_path: Path = UPTIME_MONITORS_PATH, catalog_path: Path = HEALTH_PROBE_CATALOG_PATH
) -> None:
    catalog = load_health_probe_catalog(catalog_path)
    monitors = build_uptime_monitors(catalog)
    write_json(output_path, monitors, indent=2, sort_keys=False)
    output_path.write_text(render_uptime_monitors(monitors), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render the repo-managed Uptime Kuma monitor list from the health probe catalog."
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=HEALTH_PROBE_CATALOG_PATH,
        help="Health probe catalog to read.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=UPTIME_MONITORS_PATH,
        help="Uptime monitor file to write or validate.",
    )
    parser.add_argument("--write", action="store_true", help="Write the generated monitor file.")
    parser.add_argument("--check", action="store_true", help="Fail if the generated file is stale.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if not args.write and not args.check:
            parser.error("one of --write or --check is required")
        if args.write:
            write_uptime_monitors(output_path=args.output, catalog_path=args.catalog)
            return 0
        if outputs_match(output_path=args.output, catalog_path=args.catalog):
            return 0
        raise ValueError(f"{args.output} is stale; run 'python3 scripts/uptime_contract.py --write' to regenerate it")
    except Exception as exc:
        return emit_cli_error("uptime contract", exc)


if __name__ == "__main__":
    raise SystemExit(main())
