from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from platform.world_state.client import StaleDataError, SurfaceNotFoundError, WorldStateClient


def prepare_world_state_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE world_state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surface TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            data TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE world_state_current_view (
            surface TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            is_expired INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.executemany(
        "INSERT INTO world_state_snapshots (surface, collected_at, data, stale) VALUES (?, ?, ?, ?)",
        [
            ("service_health", "2026-03-24T09:00:00+00:00", json.dumps({"services": [{"service_id": "grafana"}]}), 0),
            ("service_health", "2026-03-24T09:05:00+00:00", json.dumps({"services": [{"service_id": "windmill"}]}), 0),
            ("dns_records", "2026-03-24T09:10:00+00:00", json.dumps([{"fqdn": "grafana.example.com"}]), 1),
        ],
    )
    connection.executemany(
        "INSERT INTO world_state_current_view (surface, data, collected_at, stale, is_expired) VALUES (?, ?, ?, ?, ?)",
        [
            (
                "service_health",
                json.dumps({"services": [{"service_id": "windmill"}]}),
                "2026-03-24T09:05:00+00:00",
                0,
                0,
            ),
            ("dns_records", json.dumps([{"fqdn": "grafana.example.com"}]), "2026-03-24T09:10:00+00:00", 1, 1),
        ],
    )
    connection.commit()
    connection.close()
    return path


@pytest.fixture()
def client_db(tmp_path: Path) -> WorldStateClient:
    db_path = prepare_world_state_db(tmp_path / "world-state.sqlite3")
    return WorldStateClient(
        dsn=f"sqlite:///{db_path}",
        current_view_name="world_state_current_view",
        snapshots_table_name="world_state_snapshots",
    )


def test_get_returns_surface_payload(client_db: WorldStateClient) -> None:
    payload = client_db.get("service_health")
    assert payload["services"][0]["service_id"] == "windmill"


def test_get_raises_for_stale_surface(client_db: WorldStateClient) -> None:
    with pytest.raises(StaleDataError):
        client_db.get("dns_records")


def test_get_at_returns_historical_snapshot(client_db: WorldStateClient) -> None:
    payload = client_db.get_at("service_health", at="2026-03-24T09:01:00Z")
    assert payload["services"][0]["service_id"] == "grafana"


def test_list_stale_returns_expired_surfaces(client_db: WorldStateClient) -> None:
    stale = client_db.list_stale()
    assert [snapshot.surface for snapshot in stale] == ["dns_records"]


def test_missing_surface_raises(client_db: WorldStateClient) -> None:
    with pytest.raises(SurfaceNotFoundError):
        client_db.get("proxmox_vms")


def test_repo_snapshot_mode_reads_local_surface(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / ".local" / "state" / "world-state"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "proxmox_vms.json").write_text(
        json.dumps({"items": [{"service_id": "netbox", "vmid": 130}], "stale": False}) + "\n",
        encoding="utf-8",
    )

    client = WorldStateClient(tmp_path)

    payload = client.get("proxmox_vms")

    assert payload["items"][0]["vmid"] == 130


def test_platform_package_preserves_stdlib_api(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root))
    sys.modules.pop("platform", None)
    imported = importlib.import_module("platform")

    assert callable(imported.system)
    assert isinstance(imported.system(), str)
    imported_world_state = importlib.import_module("platform.world_state.client")
    assert hasattr(imported_world_state, "WorldStateClient")
