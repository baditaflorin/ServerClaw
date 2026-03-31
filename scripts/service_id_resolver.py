#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from typing import Final

from controller_automation_toolkit import load_json, load_yaml, repo_path


SERVICE_CATALOG_PATH: Final = repo_path("config", "service-capability-catalog.json")
EXECUTION_SCOPES_PATH: Final = repo_path("config", "ansible-execution-scopes.yaml")


def load_service_catalog_ids() -> set[str]:
    payload = load_json(SERVICE_CATALOG_PATH)
    services = payload.get("services", [])
    return {
        str(service.get("id")).strip()
        for service in services
        if isinstance(service, dict) and isinstance(service.get("id"), str) and service.get("id", "").strip()
    }


def load_service_aliases() -> dict[str, str]:
    payload = load_yaml(EXECUTION_SCOPES_PATH)
    playbooks = payload.get("playbooks", {})
    aliases: dict[str, str] = {}
    if not isinstance(playbooks, dict):
        return aliases

    for raw_entry in playbooks.values():
        if not isinstance(raw_entry, dict):
            continue
        playbook_id = raw_entry.get("playbook_id")
        canonical_service_id = raw_entry.get("canonical_service_id")
        if not isinstance(playbook_id, str) or not playbook_id.strip():
            continue
        if not isinstance(canonical_service_id, str) or not canonical_service_id.strip():
            continue
        aliases[playbook_id.strip()] = canonical_service_id.strip()
    return aliases


def resolve_service_id(service_id: str) -> str:
    normalized = service_id.strip()
    if not normalized:
        return normalized
    if normalized in load_service_catalog_ids():
        return normalized
    return load_service_aliases().get(normalized, normalized)


def exists_in_catalog(service_id: str) -> bool:
    return resolve_service_id(service_id) in load_service_catalog_ids()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve and inspect governed service ids.")
    parser.add_argument("--resolve", help="Resolve one requested service id through the service catalog and alias map.")
    parser.add_argument(
        "--exists-in-catalog",
        metavar="SERVICE_ID",
        help="Exit 0 when the requested id resolves to a service capability catalog entry, else exit 1.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if bool(args.resolve) == bool(args.exists_in_catalog):
        parser.print_help()
        return 0

    if args.resolve:
        print(resolve_service_id(args.resolve))
        return 0

    return 0 if exists_in_catalog(args.exists_in_catalog) else 1


if __name__ == "__main__":
    sys.exit(main())
