#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from validation_toolkit import require_list, require_mapping, require_str

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
    ) from exc


SCHEMA_VERSION = "1.0.0"
BUNDLE_ROOT = repo_path("catalog", "services")
METADATA_PATH = BUNDLE_ROOT / "_metadata.yaml"
BUNDLE_FILE = "service.yaml"

SERVICE_BUNDLE_SCHEMA_PATH = repo_path("docs", "schema", "service-definition-bundle.schema.json")
METADATA_SCHEMA_PATH = repo_path("docs", "schema", "service-definition-metadata.schema.json")
HEALTH_FRAGMENT_SCHEMA_PATH = repo_path(
    "docs",
    "schema",
    "service-definition-health-fragment.schema.json",
)
DATA_FRAGMENT_SCHEMA_PATH = repo_path(
    "docs",
    "schema",
    "service-definition-data-fragment.schema.json",
)
SLO_FRAGMENT_SCHEMA_PATH = repo_path(
    "docs",
    "schema",
    "service-definition-slo-fragment.schema.json",
)
COMPLETENESS_FRAGMENT_SCHEMA_PATH = repo_path(
    "docs",
    "schema",
    "service-definition-completeness-fragment.schema.json",
)
REDUNDANCY_FRAGMENT_SCHEMA_PATH = repo_path(
    "docs",
    "schema",
    "service-definition-redundancy-fragment.schema.json",
)
DEPENDENCY_FRAGMENT_SCHEMA_PATH = repo_path(
    "docs",
    "schema",
    "service-definition-dependency-fragment.schema.json",
)

SERVICE_CAPABILITY_SCHEMA_PATH = repo_path("docs", "schema", "service-capability-catalog.schema.json")
SERVICE_COMPLETENESS_SCHEMA_PATH = repo_path("docs", "schema", "service-completeness.schema.json")
SERVICE_REDUNDANCY_SCHEMA_PATH = repo_path("docs", "schema", "service-redundancy-catalog.schema.json")
DEPENDENCY_GRAPH_SCHEMA_PATH = repo_path("docs", "schema", "dependency-graph.schema.json")
DATA_CATALOG_SCHEMA_PATH = repo_path("docs", "schema", "data-catalog.schema.json")
SLO_CATALOG_SCHEMA_PATH = repo_path("docs", "schema", "slo-catalog.schema.json")
HEALTH_PROBE_CATALOG_SCHEMA_PATH = repo_path("docs", "schema", "health-probe-catalog.schema.json")

FRAGMENT_SPECS: dict[str, dict[str, Any]] = {
    "health": {
        "filename": "health.yaml",
        "schema_path": HEALTH_FRAGMENT_SCHEMA_PATH,
        "type": "mapping",
        "required": False,
    },
    "data": {
        "filename": "data.yaml",
        "schema_path": DATA_FRAGMENT_SCHEMA_PATH,
        "type": "list",
        "required": False,
    },
    "slos": {
        "filename": "slo.yaml",
        "schema_path": SLO_FRAGMENT_SCHEMA_PATH,
        "type": "list",
        "required": False,
    },
    "completeness": {
        "filename": "completeness.yaml",
        "schema_path": COMPLETENESS_FRAGMENT_SCHEMA_PATH,
        "type": "mapping",
        "required": True,
    },
    "redundancy": {
        "filename": "redundancy.yaml",
        "schema_path": REDUNDANCY_FRAGMENT_SCHEMA_PATH,
        "type": "mapping",
        "required": True,
    },
    "dependency": {
        "filename": "dependency.yaml",
        "schema_path": DEPENDENCY_FRAGMENT_SCHEMA_PATH,
        "type": "mapping",
        "required": True,
    },
}

OUTPUT_SPECS: dict[str, dict[str, Any]] = {
    "service_capability_catalog": {
        "path": repo_path("config", "service-capability-catalog.json"),
    },
    "health_probe_catalog": {
        "path": repo_path("config", "health-probe-catalog.json"),
    },
    "service_completeness": {
        "path": repo_path("config", "service-completeness.json"),
    },
    "service_redundancy": {
        "path": repo_path("config", "service-redundancy-catalog.json"),
    },
    "dependency_graph": {
        "path": repo_path("config", "dependency-graph.json"),
    },
    "data_catalog": {
        "path": repo_path("config", "data-catalog.json"),
    },
    "slo_catalog": {
        "path": repo_path("config", "slo-catalog.json"),
    },
}


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:  # pragma: no cover - exercised through dump
        return True

    def increase_indent(
        self, flow: bool = False, indentless: bool = False
    ) -> Any:  # pragma: no cover - exercised through dump
        # Keep sequence entries indented beneath their parent key so the emitted
        # bundle YAML satisfies the repository yamllint profile.
        return super().increase_indent(flow, False)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            payload,
            Dumper=_NoAliasDumper,
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"{label} does not match {schema_path.name}: {exc.message}") from exc


def metadata_path(bundle_root: Path = BUNDLE_ROOT) -> Path:
    return bundle_root / "_metadata.yaml"


def bundle_repo_root(bundle_root: Path = BUNDLE_ROOT) -> Path:
    return bundle_root.resolve().parents[1]


def resolve_output_path(relative_path: str, *, bundle_root: Path = BUNDLE_ROOT) -> Path:
    return bundle_repo_root(bundle_root) / relative_path


def service_bundle_dir(service_id: str, bundle_root: Path = BUNDLE_ROOT) -> Path:
    return bundle_root / service_id


def service_bundle_path(service_id: str, bundle_root: Path = BUNDLE_ROOT) -> Path:
    return service_bundle_dir(service_id, bundle_root) / BUNDLE_FILE


def load_service_definition_metadata(path: Path = METADATA_PATH) -> dict[str, Any]:
    payload = require_mapping(load_yaml(path), str(path))
    validate_schema(payload, METADATA_SCHEMA_PATH, str(path))
    return payload


def _validate_fragment_payload(fragment_name: str, payload: dict[str, Any], path: Path) -> Any:
    spec = FRAGMENT_SPECS[fragment_name]
    validate_schema(payload, spec["schema_path"], str(path))
    section = payload.get(fragment_name)
    if spec["type"] == "mapping":
        return require_mapping(section, f"{path}.{fragment_name}")
    if spec["type"] == "list":
        return require_list(section, f"{path}.{fragment_name}")
    raise ValueError(f"unsupported fragment type for {fragment_name}")


def _load_service_bundle_section(
    bundle_dir: Path,
    bundle_payload: dict[str, Any],
    section_name: str,
) -> Any:
    inline_value = bundle_payload.get(section_name)
    fragment_path = bundle_dir / FRAGMENT_SPECS[section_name]["filename"]
    fragment_value = None
    if fragment_path.exists():
        fragment_payload = require_mapping(load_yaml(fragment_path), str(fragment_path))
        fragment_value = _validate_fragment_payload(section_name, fragment_payload, fragment_path)

    if inline_value is not None and fragment_value is not None:
        raise ValueError(
            f"{bundle_dir.name} must declare {section_name} in either {BUNDLE_FILE} or {fragment_path.name}, not both"
        )
    if fragment_value is not None:
        return fragment_value

    if inline_value is None:
        if FRAGMENT_SPECS[section_name]["required"]:
            raise ValueError(f"{bundle_dir.name} is missing required section '{section_name}'")
        return [] if FRAGMENT_SPECS[section_name]["type"] == "list" else None

    if FRAGMENT_SPECS[section_name]["type"] == "mapping":
        return require_mapping(inline_value, f"{bundle_dir / BUNDLE_FILE}.{section_name}")
    return require_list(inline_value, f"{bundle_dir / BUNDLE_FILE}.{section_name}")


def load_service_bundle(bundle_dir: Path) -> dict[str, Any]:
    bundle_path = bundle_dir / BUNDLE_FILE
    payload = require_mapping(load_yaml(bundle_path), str(bundle_path))
    validate_schema(payload, SERVICE_BUNDLE_SCHEMA_PATH, str(bundle_path))

    service = require_mapping(payload.get("service"), f"{bundle_path}.service")
    service_id = require_str(service.get("id"), f"{bundle_path}.service.id")
    if bundle_dir.name != service_id:
        raise ValueError(
            f"{bundle_path} declares service.id '{service_id}' but the directory name is '{bundle_dir.name}'"
        )

    dependency = require_mapping(
        _load_service_bundle_section(bundle_dir, payload, "dependency"),
        f"{bundle_path}.dependency",
    )
    dependency_node = require_mapping(
        dependency.get("node"),
        f"{bundle_path}.dependency.node",
    )
    outbound_edges = require_list(
        dependency.get("outbound_edges", []),
        f"{bundle_path}.dependency.outbound_edges",
    )

    return {
        "service_id": service_id,
        "service": service,
        "health": _load_service_bundle_section(bundle_dir, payload, "health"),
        "completeness": require_mapping(
            _load_service_bundle_section(bundle_dir, payload, "completeness"),
            f"{bundle_path}.completeness",
        ),
        "redundancy": require_mapping(
            _load_service_bundle_section(bundle_dir, payload, "redundancy"),
            f"{bundle_path}.redundancy",
        ),
        "dependency": {
            "node": dependency_node,
            "outbound_edges": outbound_edges,
        },
        "data": require_list(
            _load_service_bundle_section(bundle_dir, payload, "data"),
            f"{bundle_path}.data",
        ),
        "slos": require_list(
            _load_service_bundle_section(bundle_dir, payload, "slos"),
            f"{bundle_path}.slos",
        ),
        "bundle_dir": bundle_dir,
        "bundle_path": bundle_path,
    }


def iter_service_bundle_dirs(bundle_root: Path = BUNDLE_ROOT) -> list[Path]:
    if not bundle_root.exists():
        raise ValueError(f"missing service bundle root: {bundle_root}")
    dirs = [path for path in bundle_root.iterdir() if path.is_dir() and not path.name.startswith("_")]
    return sorted(dirs, key=lambda path: path.name)


def load_service_bundle_index(bundle_root: Path = BUNDLE_ROOT) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for bundle_dir in iter_service_bundle_dirs(bundle_root):
        bundle = load_service_bundle(bundle_dir)
        service_id = bundle["service_id"]
        if service_id in index:
            raise ValueError(f"duplicate service bundle id '{service_id}'")
        index[service_id] = bundle
    if not index:
        raise ValueError(f"{bundle_root} must contain at least one service bundle")
    return index


def _sorted_mapping(items: dict[str, Any]) -> dict[str, Any]:
    return {key: items[key] for key in sorted(items)}


def _sorted_list(items: list[dict[str, Any]], *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: tuple(str(item.get(key, "")) for key in keys),
    )


def build_aggregate_catalogs(
    *,
    metadata: dict[str, Any] | None = None,
    bundle_index: dict[str, dict[str, Any]] | None = None,
    bundle_root: Path = BUNDLE_ROOT,
) -> dict[str, Any]:
    metadata = metadata or load_service_definition_metadata(metadata_path(bundle_root))
    bundle_index = bundle_index or load_service_bundle_index(bundle_root)

    service_entries = [deepcopy(bundle_index[service_id]["service"]) for service_id in sorted(bundle_index)]
    health_services = {
        service_id: deepcopy(bundle["health"])
        for service_id, bundle in sorted(bundle_index.items())
        if bundle["health"] is not None
    }
    completeness_services = {
        service_id: deepcopy(bundle_index[service_id]["completeness"]) for service_id in sorted(bundle_index)
    }
    redundancy_services = {
        service_id: deepcopy(bundle_index[service_id]["redundancy"]) for service_id in sorted(bundle_index)
    }
    dependency_nodes = [deepcopy(bundle_index[service_id]["dependency"]["node"]) for service_id in sorted(bundle_index)]
    dependency_edges: list[dict[str, Any]] = []
    for service_id in sorted(bundle_index):
        dependency_edges.extend(deepcopy(bundle_index[service_id]["dependency"]["outbound_edges"]))
    dependency_edges = _sorted_list(
        dependency_edges,
        keys=("from", "to", "type", "description"),
    )

    data_stores: list[dict[str, Any]] = []
    for service_id in sorted(bundle_index):
        data_stores.extend(deepcopy(bundle_index[service_id]["data"]))
    data_stores = _sorted_list(data_stores, keys=("service", "id"))

    slos: list[dict[str, Any]] = []
    for service_id in sorted(bundle_index):
        slos.extend(deepcopy(bundle_index[service_id]["slos"]))
    slos = _sorted_list(slos, keys=("service_id", "service", "id"))

    outputs = metadata["outputs"]
    assembled = {
        "service_capability_catalog": {
            **deepcopy(outputs["service_capability_catalog"]["top_level"]),
            "services": service_entries,
        },
        "health_probe_catalog": {
            **deepcopy(outputs["health_probe_catalog"]["top_level"]),
            "services": _sorted_mapping(health_services),
        },
        "service_completeness": {
            **deepcopy(outputs["service_completeness"]["top_level"]),
            "services": _sorted_mapping(completeness_services),
        },
        "service_redundancy": {
            **deepcopy(outputs["service_redundancy"]["top_level"]),
            "services": _sorted_mapping(redundancy_services),
        },
        "dependency_graph": {
            **deepcopy(outputs["dependency_graph"]["top_level"]),
            "nodes": _sorted_list(dependency_nodes, keys=("id",)),
            "edges": dependency_edges,
        },
        "data_catalog": {
            **deepcopy(outputs["data_catalog"]["top_level"]),
            "data_stores": data_stores,
        },
        "slo_catalog": {
            **deepcopy(outputs["slo_catalog"]["top_level"]),
            "slos": slos,
        },
    }
    return assembled


def validate_aggregate_catalogs(catalogs: dict[str, Any]) -> None:
    for output_name, payload in catalogs.items():
        declared_schema = None
        if isinstance(payload, dict):
            declared_schema = payload.get("$schema")
        if isinstance(declared_schema, str) and declared_schema.strip():
            validate_schema(payload, repo_path(declared_schema), output_name)
            continue
        if output_name == "health_probe_catalog":
            validate_schema(payload, HEALTH_PROBE_CATALOG_SCHEMA_PATH, output_name)


def write_aggregate_catalogs(
    catalogs: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
    bundle_root: Path = BUNDLE_ROOT,
) -> None:
    metadata = metadata or load_service_definition_metadata(metadata_path(bundle_root))
    for output_name, payload in catalogs.items():
        output_path = resolve_output_path(metadata["outputs"][output_name]["path"], bundle_root=bundle_root)
        write_json(output_path, payload)


def check_aggregate_catalogs(
    catalogs: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
    bundle_root: Path = BUNDLE_ROOT,
) -> None:
    metadata = metadata or load_service_definition_metadata(metadata_path(bundle_root))
    for output_name, payload in catalogs.items():
        output_path = resolve_output_path(metadata["outputs"][output_name]["path"], bundle_root=bundle_root)
        current = load_json(output_path)
        if current != payload:
            raise ValueError(
                f"{output_path.relative_to(bundle_repo_root(bundle_root))} does not match the assembled service bundles; run scripts/service_definition_catalog.py --write"
            )


def _top_level_without(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    result = deepcopy(payload)
    for key in keys:
        result.pop(key, None)
    return result


def migrate_from_aggregate_catalogs(
    *,
    bundle_root: Path = BUNDLE_ROOT,
    overwrite: bool = False,
) -> None:
    repo_root = bundle_repo_root(bundle_root)
    service_catalog = require_mapping(
        load_json(repo_root / "config" / "service-capability-catalog.json"),
        "config/service-capability-catalog.json",
    )
    health_catalog = require_mapping(
        load_json(repo_root / "config" / "health-probe-catalog.json"),
        "config/health-probe-catalog.json",
    )
    completeness_catalog = require_mapping(
        load_json(repo_root / "config" / "service-completeness.json"),
        "config/service-completeness.json",
    )
    redundancy_catalog = require_mapping(
        load_json(repo_root / "config" / "service-redundancy-catalog.json"),
        "config/service-redundancy-catalog.json",
    )
    dependency_graph = require_mapping(
        load_json(repo_root / "config" / "dependency-graph.json"),
        "config/dependency-graph.json",
    )
    data_catalog = require_mapping(
        load_json(repo_root / "config" / "data-catalog.json"),
        "config/data-catalog.json",
    )
    slo_catalog = require_mapping(
        load_json(repo_root / "config" / "slo-catalog.json"),
        "config/slo-catalog.json",
    )

    services = require_list(service_catalog.get("services"), "config/service-capability-catalog.json.services")
    health_services = require_mapping(health_catalog.get("services"), "config/health-probe-catalog.json.services")
    completeness_services = require_mapping(
        completeness_catalog.get("services"),
        "config/service-completeness.json.services",
    )
    redundancy_services = require_mapping(
        redundancy_catalog.get("services"),
        "config/service-redundancy-catalog.json.services",
    )
    dependency_nodes = require_list(dependency_graph.get("nodes"), "config/dependency-graph.json.nodes")
    dependency_edges = require_list(dependency_graph.get("edges"), "config/dependency-graph.json.edges")
    data_stores = require_list(data_catalog.get("data_stores"), "config/data-catalog.json.data_stores")
    slos = require_list(slo_catalog.get("slos"), "config/slo-catalog.json.slos")

    node_by_id: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(dependency_nodes):
        node = require_mapping(node, f"config/dependency-graph.json.nodes[{index}]")
        node_id = require_str(node.get("id"), f"config/dependency-graph.json.nodes[{index}].id")
        if node_id in node_by_id:
            raise ValueError(f"duplicate dependency node id '{node_id}'")
        node_by_id[node_id] = node

    edges_by_source: dict[str, list[dict[str, Any]]] = {}
    for index, edge in enumerate(dependency_edges):
        edge = require_mapping(edge, f"config/dependency-graph.json.edges[{index}]")
        source = require_str(edge.get("from"), f"config/dependency-graph.json.edges[{index}].from")
        edges_by_source.setdefault(source, []).append(edge)

    data_by_service: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(data_stores):
        entry = require_mapping(entry, f"config/data-catalog.json.data_stores[{index}]")
        service_id = require_str(entry.get("service"), f"config/data-catalog.json.data_stores[{index}].service")
        data_by_service.setdefault(service_id, []).append(entry)

    slos_by_service: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(slos):
        entry = require_mapping(entry, f"config/slo-catalog.json.slos[{index}]")
        service_id = require_str(
            entry.get("service_id", entry.get("service")),
            f"config/slo-catalog.json.slos[{index}].service_id",
        )
        slos_by_service.setdefault(service_id, []).append(entry)

    metadata_payload = {
        "schema_version": SCHEMA_VERSION,
        "outputs": {
            "service_capability_catalog": {
                "path": "config/service-capability-catalog.json",
                "top_level": _top_level_without(service_catalog, "services"),
            },
            "health_probe_catalog": {
                "path": "config/health-probe-catalog.json",
                "top_level": _top_level_without(health_catalog, "services"),
            },
            "service_completeness": {
                "path": "config/service-completeness.json",
                "top_level": _top_level_without(completeness_catalog, "services"),
            },
            "service_redundancy": {
                "path": "config/service-redundancy-catalog.json",
                "top_level": _top_level_without(redundancy_catalog, "services"),
            },
            "dependency_graph": {
                "path": "config/dependency-graph.json",
                "top_level": _top_level_without(dependency_graph, "nodes", "edges"),
            },
            "data_catalog": {
                "path": "config/data-catalog.json",
                "top_level": _top_level_without(data_catalog, "data_stores"),
            },
            "slo_catalog": {
                "path": "config/slo-catalog.json",
                "top_level": _top_level_without(slo_catalog, "slos"),
            },
        },
    }

    bundle_root.mkdir(parents=True, exist_ok=True)
    metadata_file = metadata_path(bundle_root)
    if metadata_file.exists() and not overwrite:
        raise ValueError(
            f"{metadata_file.relative_to(repo_root)} already exists; rerun with --overwrite-bundles to replace it"
        )
    write_yaml(metadata_file, metadata_payload)

    for service in services:
        service = require_mapping(service, "config/service-capability-catalog.json.services[]")
        service_id = require_str(service.get("id"), "config/service-capability-catalog.json.services[].id")
        if service_id not in completeness_services:
            raise ValueError(f"missing service completeness entry for {service_id}")
        if service_id not in redundancy_services:
            raise ValueError(f"missing service redundancy entry for {service_id}")
        if service_id not in node_by_id:
            raise ValueError(f"missing dependency node for {service_id}")

        service_dir = service_bundle_dir(service_id, bundle_root)
        bundle_file = service_dir / BUNDLE_FILE
        if service_dir.exists() and not overwrite:
            raise ValueError(
                f"{service_dir.relative_to(repo_root)} already exists; rerun with --overwrite-bundles to replace it"
            )
        service_dir.mkdir(parents=True, exist_ok=True)

        bundle_payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "service": deepcopy(service),
            "completeness": deepcopy(completeness_services[service_id]),
            "redundancy": deepcopy(redundancy_services[service_id]),
            "dependency": {
                "node": deepcopy(node_by_id[service_id]),
                "outbound_edges": deepcopy(
                    _sorted_list(edges_by_source.get(service_id, []), keys=("from", "to", "type", "description"))
                ),
            },
        }
        if service_id in health_services:
            bundle_payload["health"] = deepcopy(health_services[service_id])
        if service_id in data_by_service:
            bundle_payload["data"] = deepcopy(_sorted_list(data_by_service[service_id], keys=("service", "id")))
        if service_id in slos_by_service:
            bundle_payload["slos"] = deepcopy(
                _sorted_list(slos_by_service[service_id], keys=("service_id", "service", "id"))
            )
        write_yaml(bundle_file, bundle_payload)


def scaffold_service_bundle_payload(
    *,
    service_entry: dict[str, Any],
    completeness_entry: dict[str, Any],
    redundancy_entry: dict[str, Any],
    dependency_node: dict[str, Any],
    dependency_edges: list[dict[str, Any]],
    health_entry: dict[str, Any] | None = None,
    data_entries: list[dict[str, Any]] | None = None,
    slo_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "service": deepcopy(service_entry),
        "completeness": deepcopy(completeness_entry),
        "redundancy": deepcopy(redundancy_entry),
        "dependency": {
            "node": deepcopy(dependency_node),
            "outbound_edges": deepcopy(dependency_edges),
        },
    }
    if health_entry is not None:
        payload["health"] = deepcopy(health_entry)
    if data_entries:
        payload["data"] = deepcopy(data_entries)
    if slo_entries:
        payload["slos"] = deepcopy(slo_entries)
    return payload


def write_scaffold_service_bundle(
    service_id: str,
    payload: dict[str, Any],
    *,
    bundle_root: Path = BUNDLE_ROOT,
) -> None:
    service_dir = service_bundle_dir(service_id, bundle_root)
    service_dir.mkdir(parents=True, exist_ok=True)
    write_yaml(service_dir / BUNDLE_FILE, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble generated service catalogs from catalog/services/<service-id>/ bundles."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the assembled aggregate catalogs back to config/.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed aggregate catalogs do not match the assembled bundles.",
    )
    parser.add_argument(
        "--migrate-from-aggregates",
        action="store_true",
        help="Seed catalog/services/ bundles and _metadata.yaml from the current aggregate catalogs.",
    )
    parser.add_argument(
        "--overwrite-bundles",
        action="store_true",
        help="Allow --migrate-from-aggregates to replace existing bundle files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv or sys.argv[1:])

    if not any((args.write, args.check, args.migrate_from_aggregates)):
        parser.print_help()
        return 0

    try:
        if args.migrate_from_aggregates:
            migrate_from_aggregate_catalogs(overwrite=args.overwrite_bundles)

        if args.write or args.check:
            metadata = load_service_definition_metadata()
            bundle_index = load_service_bundle_index()
            catalogs = build_aggregate_catalogs(metadata=metadata, bundle_index=bundle_index)
            validate_aggregate_catalogs(catalogs)
            if args.write:
                write_aggregate_catalogs(catalogs, metadata=metadata)
            if args.check:
                check_aggregate_catalogs(catalogs, metadata=metadata)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Service definition catalog", exc)

    if args.check and not args.write:
        print("Service definition catalog OK")
    elif args.write:
        print("Service definition catalog written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
