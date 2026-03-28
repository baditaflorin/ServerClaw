#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
    ) from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_CONTRACT_CATALOG_PATH = REPO_ROOT / "config" / "capability-contract-catalog.json"
CAPABILITY_CONTRACT_SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "capability-contract-catalog.schema.json"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
ADR_DIR = REPO_ROOT / "docs" / "adr"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def emit_cli_error(label: str, exc: Exception) -> int:
    print(f"{label} error: {exc}", file=sys.stderr)
    return 1


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    values = [require_str(item, f"{path}[{index}]") for index, item in enumerate(items)]
    if len(values) != len(set(values)):
        raise ValueError(f"{path} must not contain duplicates")
    return values


def resolve_adr_path(adr_id: str) -> Path:
    matches = sorted(ADR_DIR.glob(f"{adr_id}-*.md"))
    if not matches:
        raise ValueError(f"docs/adr/{adr_id}-*.md does not exist")
    if len(matches) > 1:
        raise ValueError(f"docs/adr/{adr_id}-*.md is ambiguous")
    return matches[0]


def load_capability_contract_catalog(path: Path = CAPABILITY_CONTRACT_CATALOG_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def load_service_catalog(path: Path = SERVICE_CATALOG_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def validate_capability_contract_catalog(
    catalog: dict[str, Any],
    *,
    service_catalog: dict[str, Any] | None = None,
    catalog_path: Path = CAPABILITY_CONTRACT_CATALOG_PATH,
) -> None:
    jsonschema.validate(
        instance=catalog,
        schema=load_json(CAPABILITY_CONTRACT_SCHEMA_PATH),
    )

    services = load_service_catalog() if service_catalog is None else service_catalog
    service_entries = require_list(services.get("services"), "config/service-capability-catalog.json.services")
    service_index = {
        require_str(service.get("id"), f"config/service-capability-catalog.json.services[{index}].id"): require_mapping(
            service,
            f"config/service-capability-catalog.json.services[{index}]",
        )
        for index, service in enumerate(service_entries)
    }

    capabilities = require_list(catalog.get("capabilities"), f"{catalog_path}.capabilities")
    if not capabilities:
        raise ValueError(f"{catalog_path}.capabilities must not be empty")

    seen_ids: set[str] = set()
    for index, raw_capability in enumerate(capabilities):
        path = f"{catalog_path}.capabilities[{index}]"
        capability = require_mapping(raw_capability, path)
        capability_id = require_str(capability.get("id"), f"{path}.id")
        if capability_id in seen_ids:
            raise ValueError(f"{path}.id duplicates capability '{capability_id}'")
        seen_ids.add(capability_id)

        require_string_list(capability.get("required_outcomes"), f"{path}.required_outcomes")
        require_string_list(capability.get("service_guarantees"), f"{path}.service_guarantees")
        require_string_list(capability.get("security_expectations"), f"{path}.security_expectations")
        require_string_list(capability.get("audit_expectations"), f"{path}.audit_expectations")
        require_string_list(capability.get("observability_requirements"), f"{path}.observability_requirements")
        require_string_list(capability.get("portability_constraints"), f"{path}.portability_constraints")

        migration = require_mapping(capability.get("migration_expectations"), f"{path}.migration_expectations")
        require_string_list(migration.get("export_formats"), f"{path}.migration_expectations.export_formats")
        require_string_list(
            migration.get("import_requirements"),
            f"{path}.migration_expectations.import_requirements",
        )
        require_str(
            migration.get("fallback_behaviour"),
            f"{path}.migration_expectations.fallback_behaviour",
        )

        failure_modes = require_list(capability.get("failure_modes"), f"{path}.failure_modes")
        if not failure_modes:
            raise ValueError(f"{path}.failure_modes must not be empty")
        for failure_index, raw_failure in enumerate(failure_modes):
            failure_path = f"{path}.failure_modes[{failure_index}]"
            failure = require_mapping(raw_failure, failure_path)
            require_str(failure.get("mode"), f"{failure_path}.mode")
            require_str(failure.get("acceptable_degradation"), f"{failure_path}.acceptable_degradation")
            require_str(failure.get("operator_response"), f"{failure_path}.operator_response")

        for field_name in ("canonical_inputs", "canonical_outputs"):
            entries = require_list(capability.get(field_name), f"{path}.{field_name}")
            if not entries:
                raise ValueError(f"{path}.{field_name} must not be empty")
            for entry_index, raw_entry in enumerate(entries):
                entry_path = f"{path}.{field_name}[{entry_index}]"
                entry = require_mapping(raw_entry, entry_path)
                require_str(entry.get("name"), f"{entry_path}.name")
                require_str(entry.get("description"), f"{entry_path}.description")

        selection = capability.get("current_selection")
        if selection is None:
            continue

        selection = require_mapping(selection, f"{path}.current_selection")
        service_id = require_str(selection.get("service_id"), f"{path}.current_selection.service_id")
        if service_id not in service_index:
            raise ValueError(
                f"{path}.current_selection.service_id references unknown service '{service_id}'"
            )
        adr_id = require_str(selection.get("selection_adr"), f"{path}.current_selection.selection_adr")
        resolve_adr_path(adr_id)
        runbook_path = REPO_ROOT / require_str(selection.get("runbook"), f"{path}.current_selection.runbook")
        if not runbook_path.exists():
            raise ValueError(f"{path}.current_selection.runbook does not exist: {runbook_path.relative_to(REPO_ROOT)}")
        require_str(selection.get("product_name"), f"{path}.current_selection.product_name")
        require_str(selection.get("notes"), f"{path}.current_selection.notes")


def summarize_capability_contracts(
    catalog: dict[str, Any],
    *,
    service_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    services = load_service_catalog() if service_catalog is None else service_catalog
    service_entries = require_list(services.get("services"), "config/service-capability-catalog.json.services")
    service_index = {
        require_str(service.get("id"), f"config/service-capability-catalog.json.services[{index}].id"): service
        for index, service in enumerate(service_entries)
    }

    items: list[dict[str, Any]] = []
    selected_count = 0
    export_ready_count = 0

    for capability in sorted(catalog.get("capabilities", []), key=lambda item: item["id"]):
        selection = capability.get("current_selection") or {}
        service = service_index.get(selection.get("service_id", ""), {})
        export_formats = capability["migration_expectations"]["export_formats"]
        is_selected = bool(selection)
        if is_selected:
            selected_count += 1
        if export_formats:
            export_ready_count += 1
        items.append(
            {
                "id": capability["id"],
                "name": capability["name"],
                "summary": capability["summary"],
                "scope": capability["scope"],
                "owner": capability["owner"],
                "review_cadence": capability["review_cadence"],
                "selected_product": selection.get("product_name"),
                "service_id": selection.get("service_id"),
                "service_name": service.get("name"),
                "service_url": service.get("public_url") or service.get("internal_url"),
                "selection_adr": selection.get("selection_adr"),
                "runbook": selection.get("runbook"),
                "selection_notes": selection.get("notes"),
                "export_format_count": len(export_formats),
                "fallback_behaviour": capability["migration_expectations"]["fallback_behaviour"],
                "failure_mode_count": len(capability["failure_modes"]),
            }
        )

    return {
        "summary": {
            "total": len(items),
            "selected": selected_count,
            "contract_only": len(items) - selected_count,
            "export_ready": export_ready_count,
        },
        "items": items,
    }


def list_capabilities(catalog: dict[str, Any]) -> int:
    summary = summarize_capability_contracts(catalog)
    print(f"Capability contracts: {CAPABILITY_CONTRACT_CATALOG_PATH}")
    print(
        "Summary: "
        f"{summary['summary']['selected']}/{summary['summary']['total']} selected, "
        f"{summary['summary']['export_ready']} export-ready"
    )
    print("Available capability contracts:")
    for item in summary["items"]:
        selection = item["selected_product"] or "contract-only"
        print(f"  - {item['id']} [{item['scope']}] -> {selection}")
    return 0


def show_capability(catalog: dict[str, Any], capability_id: str) -> int:
    summary = summarize_capability_contracts(catalog)
    for item in summary["items"]:
        if item["id"] != capability_id:
            continue
        for raw_capability in catalog["capabilities"]:
            if raw_capability["id"] != capability_id:
                continue
            print(f"Capability: {raw_capability['id']}")
            print(f"Name: {raw_capability['name']}")
            print(f"Scope: {raw_capability['scope']}")
            print(f"Owner: {raw_capability['owner']}")
            print(f"Review cadence: {raw_capability['review_cadence']}")
            print(f"Summary: {raw_capability['summary']}")
            if item["selected_product"]:
                print(f"Selected product: {item['selected_product']}")
                if item["service_name"]:
                    print(f"Service: {item['service_name']} ({item['service_id']})")
                elif item["service_id"]:
                    print(f"Service: {item['service_id']}")
                if item["service_url"]:
                    print(f"Service URL: {item['service_url']}")
                if item["selection_adr"]:
                    print(f"Selection ADR: {item['selection_adr']}")
                if item["runbook"]:
                    print(f"Runbook: {item['runbook']}")
            else:
                print("Selected product: contract-only")
            print("Required outcomes:")
            for value in raw_capability["required_outcomes"]:
                print(f"  - {value}")
            print("Service guarantees:")
            for value in raw_capability["service_guarantees"]:
                print(f"  - {value}")
            print("Canonical inputs:")
            for value in raw_capability["canonical_inputs"]:
                print(f"  - {value['name']}: {value['description']}")
            print("Canonical outputs:")
            for value in raw_capability["canonical_outputs"]:
                print(f"  - {value['name']}: {value['description']}")
            print("Portability constraints:")
            for value in raw_capability["portability_constraints"]:
                print(f"  - {value}")
            print("Export formats:")
            for value in raw_capability["migration_expectations"]["export_formats"]:
                print(f"  - {value}")
            print("Failure modes:")
            for value in raw_capability["failure_modes"]:
                print(f"  - {value['mode']}: {value['acceptable_degradation']}")
            return 0

    print(f"Unknown capability contract: {capability_id}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate the capability contract catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the catalog and exit.")
    parser.add_argument("--list", action="store_true", help="List available capability contracts.")
    parser.add_argument("--contract", help="Print a readable summary for one capability contract id.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog = load_capability_contract_catalog()
        validate_capability_contract_catalog(catalog)
        if args.validate:
            print(f"Capability contract catalog OK: {CAPABILITY_CONTRACT_CATALOG_PATH}")
            return 0
        if args.contract:
            return show_capability(catalog, args.contract)
        return list_capabilities(catalog)
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("Capability contract catalog", exc)


if __name__ == "__main__":
    raise SystemExit(main())
