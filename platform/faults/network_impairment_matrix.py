from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX_PATH = REPO_ROOT / "config" / "network-impairment-matrix.yaml"
DEFAULT_REPORT_DIR = REPO_ROOT / ".local" / "network-impairment-matrix"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
FAULT_SCENARIO_PATH = REPO_ROOT / "config" / "fault-scenarios.yaml"

ALLOWED_ASSERTION_BEHAVIOURS = {
    "degrade_gracefully",
    "queue_and_retry",
    "fail_fast",
    "promote_standby",
    "alert_operator",
}
REQUIRED_IMPAIRMENT_IDS = {
    "added_latency",
    "packet_loss",
    "dns_resolution_failure",
    "one_way_dependency_isolation",
    "temporary_gateway_loss",
    "tls_validation_failure",
}


class NetworkImpairmentMatrixLoadError(ValueError):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - guarded by wrappers and test env
        raise RuntimeError("PyYAML is required to load the network impairment matrix") from exc
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise NetworkImpairmentMatrixLoadError(f"{path} must define a mapping at the top level")
    return payload


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NetworkImpairmentMatrixLoadError(f"{path} must be a mapping")
    return value


def _require_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NetworkImpairmentMatrixLoadError(f"{path} must be a non-empty string")
    return value.strip()


def _require_string_list(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise NetworkImpairmentMatrixLoadError(f"{path} must be a non-empty list")
    items: list[str] = []
    for index, item in enumerate(value):
        items.append(_require_non_empty_string(item, f"{path}[{index}]"))
    return tuple(items)


@dataclass(frozen=True)
class TargetClassSpec:
    name: str
    description: str
    inventory_hosts: tuple[str, ...] = ()
    maintenance_window_required: bool = False
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inventory_hosts": list(self.inventory_hosts),
            "maintenance_window_required": self.maintenance_window_required,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ImpairmentSpec:
    impairment_id: str
    description: str
    safe_target_classes: tuple[str, ...]
    blocked_target_classes: tuple[str, ...] = ()
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.impairment_id,
            "description": self.description,
            "safe_target_classes": list(self.safe_target_classes),
            "blocked_target_classes": list(self.blocked_target_classes),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class MatrixEntry:
    service: str
    dependency: str
    dependency_type: str
    expected_behaviour: str
    service_catalog_tested_by: str
    service_catalog_tested_by_implemented: bool
    target_classes: tuple[str, ...]
    impairments: tuple[str, ...]
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "dependency": self.dependency,
            "dependency_type": self.dependency_type,
            "expected_behaviour": self.expected_behaviour,
            "service_catalog_tested_by": self.service_catalog_tested_by,
            "service_catalog_tested_by_implemented": self.service_catalog_tested_by_implemented,
            "target_classes": list(self.target_classes),
            "impairments": list(self.impairments),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class MatrixCatalog:
    target_classes: dict[str, TargetClassSpec]
    impairments: dict[str, ImpairmentSpec]
    entries: tuple[MatrixEntry, ...]

    def applicable_entries(
        self,
        *,
        target_class: str | None = None,
        service: str | None = None,
    ) -> tuple[MatrixEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if (target_class is None or target_class in entry.target_classes)
            and (service is None or service == entry.service)
        )


def _load_service_catalog() -> dict[str, dict[str, Any]]:
    payload = json.loads(SERVICE_CATALOG_PATH.read_text(encoding="utf-8"))
    services = payload.get("services")
    if not isinstance(services, list):
        raise NetworkImpairmentMatrixLoadError("config/service-capability-catalog.json must define a services list")
    index: dict[str, dict[str, Any]] = {}
    for item in services:
        if not isinstance(item, dict):
            continue
        service_id = item.get("id")
        if isinstance(service_id, str) and service_id.strip():
            index[service_id.strip()] = item
    return index


def _load_fault_scenario_ids() -> set[str]:
    payload = _load_yaml(FAULT_SCENARIO_PATH)
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise NetworkImpairmentMatrixLoadError("config/fault-scenarios.yaml must define a scenarios list")
    result: set[str] = set()
    for index, item in enumerate(scenarios):
        if not isinstance(item, dict):
            raise NetworkImpairmentMatrixLoadError(f"config/fault-scenarios.yaml.scenarios[{index}] must be a mapping")
        result.add(_require_non_empty_string(item.get("name"), f"config/fault-scenarios.yaml.scenarios[{index}].name"))
    return result


def _service_dependency_contract(service: dict[str, Any], dependency: str, path: str) -> tuple[str, str]:
    modes = service.get("degradation_modes")
    if not isinstance(modes, list):
        raise NetworkImpairmentMatrixLoadError(
            f"{path} references service '{service.get('id')}' which does not declare degradation_modes"
        )
    for index, mode in enumerate(modes):
        if not isinstance(mode, dict):
            continue
        if str(mode.get("dependency", "")).strip() != dependency:
            continue
        dependency_type = _require_non_empty_string(
            mode.get("dependency_type"),
            f"{path}.degradation_modes[{index}].dependency_type",
        )
        tested_by = _require_non_empty_string(
            mode.get("tested_by"),
            f"{path}.degradation_modes[{index}].tested_by",
        )
        return dependency_type, tested_by
    raise NetworkImpairmentMatrixLoadError(
        f"{path} must reference a dependency declared in config/service-capability-catalog.json degradation_modes"
    )


def load_network_impairment_matrix(path: Path = DEFAULT_MATRIX_PATH) -> MatrixCatalog:
    payload = _load_yaml(path)
    schema_version = _require_non_empty_string(payload.get("schema_version"), f"{path}.schema_version")
    if schema_version != "1.0.0":
        raise NetworkImpairmentMatrixLoadError(f"{path} must declare schema_version '1.0.0'")

    target_payload = _require_mapping(payload.get("target_classes"), f"{path}.target_classes")
    if not target_payload:
        raise NetworkImpairmentMatrixLoadError(f"{path}.target_classes must not be empty")

    target_classes: dict[str, TargetClassSpec] = {}
    for target_name, raw in target_payload.items():
        normalized_name = _require_non_empty_string(target_name, f"{path}.target_classes key")
        raw = _require_mapping(raw, f"{path}.target_classes.{normalized_name}")
        inventory_hosts = raw.get("inventory_hosts", [])
        if inventory_hosts not in (None, []) and not isinstance(inventory_hosts, list):
            raise NetworkImpairmentMatrixLoadError(
                f"{path}.target_classes.{normalized_name}.inventory_hosts must be a list"
            )
        target_classes[normalized_name] = TargetClassSpec(
            name=normalized_name,
            description=_require_non_empty_string(
                raw.get("description"),
                f"{path}.target_classes.{normalized_name}.description",
            ),
            inventory_hosts=tuple(
                _require_non_empty_string(
                    item,
                    f"{path}.target_classes.{normalized_name}.inventory_hosts[{index}]",
                )
                for index, item in enumerate(inventory_hosts or [])
            ),
            maintenance_window_required=bool(raw.get("maintenance_window_required", False)),
            notes=str(raw.get("notes", "")).strip(),
        )

    raw_impairments = payload.get("impairments")
    if not isinstance(raw_impairments, list) or not raw_impairments:
        raise NetworkImpairmentMatrixLoadError(f"{path}.impairments must be a non-empty list")

    impairments: dict[str, ImpairmentSpec] = {}
    for index, raw in enumerate(raw_impairments):
        raw = _require_mapping(raw, f"{path}.impairments[{index}]")
        impairment_id = _require_non_empty_string(raw.get("id"), f"{path}.impairments[{index}].id")
        if impairment_id in impairments:
            raise NetworkImpairmentMatrixLoadError(f"{path} defines duplicate impairment id '{impairment_id}'")
        safe_target_classes = _require_string_list(
            raw.get("safe_target_classes"),
            f"{path}.impairments[{index}].safe_target_classes",
        )
        blocked_target_classes = tuple(
            _require_non_empty_string(
                item,
                f"{path}.impairments[{index}].blocked_target_classes[{blocked_index}]",
            )
            for blocked_index, item in enumerate(raw.get("blocked_target_classes", []))
        )
        unknown_targets = sorted((set(safe_target_classes) | set(blocked_target_classes)) - set(target_classes))
        if unknown_targets:
            raise NetworkImpairmentMatrixLoadError(
                f"{path}.impairments[{index}] references unknown target classes: {', '.join(unknown_targets)}"
            )
        overlap = sorted(set(safe_target_classes) & set(blocked_target_classes))
        if overlap:
            raise NetworkImpairmentMatrixLoadError(
                f"{path}.impairments[{index}] cannot both allow and block: {', '.join(overlap)}"
            )
        impairments[impairment_id] = ImpairmentSpec(
            impairment_id=impairment_id,
            description=_require_non_empty_string(
                raw.get("description"),
                f"{path}.impairments[{index}].description",
            ),
            safe_target_classes=safe_target_classes,
            blocked_target_classes=blocked_target_classes,
            notes=str(raw.get("notes", "")).strip(),
        )

    missing_required_impairments = sorted(REQUIRED_IMPAIRMENT_IDS - set(impairments))
    if missing_required_impairments:
        raise NetworkImpairmentMatrixLoadError(
            f"{path} is missing required impairment ids: {', '.join(missing_required_impairments)}"
        )

    service_catalog = _load_service_catalog()
    fault_scenario_ids = _load_fault_scenario_ids()
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise NetworkImpairmentMatrixLoadError(f"{path}.entries must be a non-empty list")

    entries: list[MatrixEntry] = []
    for index, raw in enumerate(raw_entries):
        raw = _require_mapping(raw, f"{path}.entries[{index}]")
        service_id = _require_non_empty_string(raw.get("service"), f"{path}.entries[{index}].service")
        service = service_catalog.get(service_id)
        if service is None:
            raise NetworkImpairmentMatrixLoadError(
                f"{path}.entries[{index}].service references unknown service '{service_id}'"
            )
        dependency = _require_non_empty_string(raw.get("dependency"), f"{path}.entries[{index}].dependency")
        dependency_type, tested_by = _service_dependency_contract(
            service,
            dependency,
            f"{path}.entries[{index}]",
        )
        expected_behaviour = _require_non_empty_string(
            raw.get("expected_behaviour"),
            f"{path}.entries[{index}].expected_behaviour",
        )
        if expected_behaviour not in ALLOWED_ASSERTION_BEHAVIOURS:
            raise NetworkImpairmentMatrixLoadError(
                f"{path}.entries[{index}].expected_behaviour must be one of {sorted(ALLOWED_ASSERTION_BEHAVIOURS)}"
            )
        service_catalog_tested_by = _require_non_empty_string(
            raw.get("service_catalog_tested_by"),
            f"{path}.entries[{index}].service_catalog_tested_by",
        )
        if service_catalog_tested_by != tested_by:
            raise NetworkImpairmentMatrixLoadError(
                f"{path}.entries[{index}].service_catalog_tested_by must match the service catalog tested_by '{tested_by}'"
            )
        target_refs = _require_string_list(
            raw.get("target_classes"),
            f"{path}.entries[{index}].target_classes",
        )
        impairment_refs = _require_string_list(
            raw.get("impairments"),
            f"{path}.entries[{index}].impairments",
        )
        unknown_targets = sorted(set(target_refs) - set(target_classes))
        if unknown_targets:
            raise NetworkImpairmentMatrixLoadError(
                f"{path}.entries[{index}] references unknown target classes: {', '.join(unknown_targets)}"
            )
        unknown_impairments = sorted(set(impairment_refs) - set(impairments))
        if unknown_impairments:
            raise NetworkImpairmentMatrixLoadError(
                f"{path}.entries[{index}] references unknown impairments: {', '.join(unknown_impairments)}"
            )
        for impairment_id in impairment_refs:
            impairment = impairments[impairment_id]
            unsupported_targets = sorted(set(target_refs) - set(impairment.safe_target_classes))
            if unsupported_targets:
                raise NetworkImpairmentMatrixLoadError(
                    f"{path}.entries[{index}] assigns impairment '{impairment_id}' to unsupported target classes: "
                    + ", ".join(unsupported_targets)
                )
            blocked_targets = sorted(set(target_refs) & set(impairment.blocked_target_classes))
            if blocked_targets:
                raise NetworkImpairmentMatrixLoadError(
                    f"{path}.entries[{index}] assigns impairment '{impairment_id}' to blocked target classes: "
                    + ", ".join(blocked_targets)
                )

        entries.append(
            MatrixEntry(
                service=service_id,
                dependency=dependency,
                dependency_type=dependency_type,
                expected_behaviour=expected_behaviour,
                service_catalog_tested_by=service_catalog_tested_by,
                service_catalog_tested_by_implemented=service_catalog_tested_by in fault_scenario_ids,
                target_classes=target_refs,
                impairments=impairment_refs,
                notes=str(raw.get("notes", "")).strip(),
            )
        )

    return MatrixCatalog(target_classes=target_classes, impairments=impairments, entries=tuple(entries))


def build_network_impairment_report(
    *,
    catalog: MatrixCatalog,
    target_class: str | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    if target_class is not None and target_class not in catalog.target_classes:
        raise NetworkImpairmentMatrixLoadError(f"unknown target class '{target_class}'")
    entries = catalog.applicable_entries(target_class=target_class, service=service)
    return {
        "status": "planned",
        "matrix_path": str(DEFAULT_MATRIX_PATH),
        "target_class": target_class,
        "service": service,
        "entry_count": len(entries),
        "target_details": catalog.target_classes[target_class].as_dict() if target_class else None,
        "available_target_classes": sorted(catalog.target_classes),
        "available_impairments": sorted(catalog.impairments),
        "entries": [entry.as_dict() for entry in entries],
    }


def render_network_impairment_report(report: dict[str, Any], *, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(report, indent=2, sort_keys=True)
    lines = [
        "ADR 0189 network impairment matrix",
        f"Status: {report['status']}",
        f"Target class: {report.get('target_class') or 'all'}",
        f"Service: {report.get('service') or 'all'}",
        f"Entries: {report['entry_count']}",
    ]
    target_details = report.get("target_details")
    if isinstance(target_details, dict):
        inventory_hosts = target_details.get("inventory_hosts") or []
        lines.append(
            "Inventory hosts: " + (", ".join(str(item) for item in inventory_hosts) if inventory_hosts else "none declared")
        )
        lines.append(
            "Maintenance window required: "
            + ("yes" if target_details.get("maintenance_window_required") else "no")
        )
    for entry in report.get("entries", []):
        lines.append(
            f"- {entry['service']} -> {entry['dependency']} [{entry['expected_behaviour']}] "
            f"targets={','.join(entry['target_classes'])} impairments={','.join(entry['impairments'])} "
            f"tested_by={entry['service_catalog_tested_by']}"
        )
    return "\n".join(lines)
