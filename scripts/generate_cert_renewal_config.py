#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from platform.datetime_compat import UTC, datetime
from tls_cert_probe import load_certificate_catalog


def build_plan() -> dict[str, Any]:
    timers: list[dict[str, Any]] = []
    sidecars: list[dict[str, Any]] = []
    unmanaged: list[dict[str, Any]] = []

    for certificate in load_certificate_catalog():
        if certificate.get("status") != "active":
            continue
        renewal = certificate["renewal"]
        entry = {
            "certificate_id": certificate["id"],
            "service_id": certificate["service_id"],
            "agent": renewal["agent"],
            "managed_by_repo": renewal["managed_by_repo"],
        }
        if renewal["managed_by_repo"] and renewal["agent"] == "systemd-step-issue":
            material = certificate.get("material", {})
            timers.append(
                {
                    **entry,
                    "host": renewal["host"],
                    "unit_name": renewal["unit_name"],
                    "on_calendar": renewal["on_calendar"],
                    "randomized_delay_seconds": renewal["randomized_delay_seconds"],
                    "reload_command": renewal["reload_command"],
                    "certificate_file": material["certificate_file"],
                    "key_file": material["key_file"],
                    "root_file": material["root_file"],
                    "subject": material["subject"],
                    "sans": material["sans"],
                    "ca_url": material["ca_url"],
                    "provisioner": material["provisioner"],
                    "password_file": material["password_file"],
                    "not_after": material["not_after"],
                }
            )
        elif renewal["managed_by_repo"] and renewal["agent"] == "compose-sidecar":
            sidecars.append(entry)
        else:
            unmanaged.append(entry)

    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "timers": sorted(timers, key=lambda item: item["certificate_id"]),
        "sidecars": sorted(sidecars, key=lambda item: item["certificate_id"]),
        "unmanaged": sorted(unmanaged, key=lambda item: item["certificate_id"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the current renewal execution plan from the certificate catalog."
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_plan()
    if args.pretty:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
