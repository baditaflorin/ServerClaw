#!/usr/bin/env python3
"""ADR 0353: Validate service integration contracts in config/integrations/.

Usage:
    python scripts/validate_integrations.py [--repo-root PATH] [--check-dead]

Checks:
  - Schema version present
  - Required fields present (contract_id, consumer, provider, integration_type)
  - contract_id matches filename (<consumer>--<provider>.yaml)
  - No duplicate contract_ids
  - Integration type is a known type
  - (optional) --check-dead: flag integrations whose consumer/provider role no longer exists
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required — run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REQUIRED_FIELDS = {"schema_version", "contract_id", "consumer", "provider", "integration_type"}
KNOWN_TYPES = {"postgres", "s3", "secrets", "oidc", "smtp", "nats", "redis", "http", "grpc"}


def load_contracts(integrations_dir: Path) -> list[tuple[Path, dict]]:
    contracts = []
    for path in sorted(integrations_dir.glob("*.yaml")):
        with path.open() as f:
            data = yaml.safe_load(f)
        contracts.append((path, data or {}))
    return contracts


def validate_contract(path: Path, data: dict) -> list[str]:
    errors = []
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        errors.append(f"missing required fields: {', '.join(sorted(missing))}")

    contract_id = data.get("contract_id", "")
    expected_stem = path.stem
    if contract_id and contract_id != expected_stem:
        errors.append(f"contract_id '{contract_id}' does not match filename '{expected_stem}'")

    integration_type = data.get("integration_type", "")
    if integration_type and integration_type not in KNOWN_TYPES:
        errors.append(f"unknown integration_type '{integration_type}' (known: {', '.join(sorted(KNOWN_TYPES))})")

    return errors


def check_dead_integrations(contracts: list[tuple[Path, dict]], roles_dir: Path) -> list[str]:
    warnings = []
    for path, data in contracts:
        for field in ("consumer", "provider"):
            role_name = data.get(field, "")
            if role_name and not (roles_dir / role_name).is_dir():
                warnings.append(f"{path.name}: {field} role '{role_name}' not found in {roles_dir}")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ADR 0353 integration contracts")
    parser.add_argument("--repo-root", default=".", help="Repository root (default: current dir)")
    parser.add_argument("--check-dead", action="store_true", help="Warn on integrations with missing roles")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    integrations_dir = repo_root / "config" / "integrations"
    roles_dir = repo_root / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"

    if not integrations_dir.is_dir():
        print(f"ERROR: {integrations_dir} does not exist", file=sys.stderr)
        return 1

    contracts = load_contracts(integrations_dir)
    if not contracts:
        print("No integration contracts found.", file=sys.stderr)
        return 0

    seen_ids: dict[str, Path] = {}
    all_errors: list[str] = []

    for path, data in contracts:
        errors = validate_contract(path, data)
        for err in errors:
            all_errors.append(f"{path.name}: {err}")
        contract_id = data.get("contract_id", "")
        if contract_id:
            if contract_id in seen_ids:
                all_errors.append(
                    f"{path.name}: duplicate contract_id '{contract_id}' (also in {seen_ids[contract_id].name})"
                )
            else:
                seen_ids[contract_id] = path

    if args.check_dead:
        warnings = check_dead_integrations(contracts, roles_dir)
        for w in warnings:
            print(f"WARN  {w}")

    if all_errors:
        for err in all_errors:
            print(f"ERROR {err}")
        print(f"\n{len(all_errors)} error(s) in {len(contracts)} contract(s).")
        return 1

    print(f"OK — {len(contracts)} integration contract(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
