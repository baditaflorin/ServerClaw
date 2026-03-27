from __future__ import annotations

import json
from pathlib import Path

import environment_catalog


def write_topology(path: Path, environments: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"schema_version": "1.0.0", "environments": environments}, indent=2) + "\n",
        encoding="utf-8",
    )


def test_configured_environment_ids_fall_back_when_topology_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    assert environment_catalog.configured_environment_ids(path) == ("production", "staging")


def test_configured_environment_ids_and_receipt_subdirectories_follow_catalog(tmp_path: Path) -> None:
    topology_path = tmp_path / "environment-topology.json"
    write_topology(
        topology_path,
        [
            {"id": "production", "status": "active"},
            {"id": "staging", "status": "planned"},
            {"id": "development", "status": "planned"},
        ],
    )

    assert environment_catalog.configured_environment_ids(topology_path) == (
        "production",
        "development",
        "staging",
    )
    assert environment_catalog.active_environment_ids(topology_path) == ("production",)
    assert environment_catalog.primary_environment(topology_path) == "production"
    assert environment_catalog.receipt_subdirectory_environments(topology_path) == {
        "development",
        "staging",
    }
