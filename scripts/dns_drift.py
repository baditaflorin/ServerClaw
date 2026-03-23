#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ipaddress
import json
from typing import Any

from controller_automation_toolkit import load_json, repo_path


SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")


def record_type_for_target(target: str) -> str:
    try:
        ipaddress.ip_address(target)
    except ValueError:
        return "CNAME"
    return "AAAA" if ":" in target else "A"


def query_records(name: str, record_type: str, dns_server: str | None = None) -> list[str]:
    import dns.resolver

    resolver = dns.resolver.Resolver(configure=True)
    if dns_server:
        resolver.nameservers = [dns_server]
    try:
        answers = resolver.resolve(name, record_type)
    except Exception:  # noqa: BLE001
        return []
    return sorted(str(answer).rstrip(".") for answer in answers)


def collect_drift(*, dns_server: str | None = None, include_planned: bool = False) -> list[dict[str, Any]]:
    payload = load_json(SUBDOMAIN_CATALOG_PATH)
    records: list[dict[str, Any]] = []
    for entry in payload.get("subdomains", []):
        if entry.get("status") != "active" and not include_planned:
            continue
        fqdn = str(entry["fqdn"])
        target = str(entry["target"]).rstrip(".")
        record_type = record_type_for_target(target)
        actual = query_records(fqdn, record_type, dns_server)
        if target in actual:
            continue
        records.append(
            {
                "source": "dns",
                "event": "platform.drift.warn",
                "severity": "warn",
                "service": entry.get("service_id"),
                "resource": fqdn,
                "record_type": record_type,
                "detail": f"expected {record_type} {target}, got {actual or ['<missing>']}",
                "expected": target,
                "actual": actual,
                "owner_adr": entry.get("owner_adr"),
                "shared_surfaces": [fqdn, str(entry.get("service_id", ""))],
            }
        )
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect DNS drift from the subdomain catalog.")
    parser.add_argument("--server", help="Optional DNS server IP.")
    parser.add_argument("--include-planned", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(collect_drift(dns_server=args.server, include_planned=args.include_planned), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
