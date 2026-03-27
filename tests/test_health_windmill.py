from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prepare_repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "versions").mkdir()
    (tmp_path / ".local" / "triage" / "reports").mkdir(parents=True)
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps({"services": [{"id": "netbox", "name": "NetBox", "lifecycle_status": "active"}]}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "versions" / "stack.yaml").write_text("repo_version: 0.1.0\nplatform_version: 0.1.0\n", encoding="utf-8")
    (tmp_path / ".local" / "triage" / "reports" / "inc-1.json").write_text(
        json.dumps({"incident_id": "inc-1", "affected_service": "netbox", "status": "firing"}) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def prepare_world_state_db(path: Path) -> str:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE world_state_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, surface TEXT NOT NULL, collected_at TEXT NOT NULL, data TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0)"
    )
    connection.execute(
        "CREATE TABLE world_state_current_view (surface TEXT PRIMARY KEY, data TEXT NOT NULL, collected_at TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0, is_expired INTEGER NOT NULL DEFAULT 0)"
    )
    connection.executemany(
        "INSERT INTO world_state_current_view (surface, data, collected_at, stale, is_expired) VALUES (?, ?, ?, ?, ?)",
        [
            (
                "service_health",
                json.dumps({"services": [{"service_id": "netbox", "status": "down"}]}),
                "2026-03-24T10:00:00+00:00",
                0,
                0,
            ),
            (
                "maintenance_windows",
                json.dumps({"active_windows": []}),
                "2026-03-24T10:00:00+00:00",
                0,
                0,
            ),
        ],
    )
    connection.commit()
    connection.close()
    return f"sqlite:///{path}"


def test_refresh_composite_wrapper_writes_critical_status(tmp_path: Path) -> None:
    repo_root = prepare_repo(tmp_path)
    dsn = prepare_world_state_db(tmp_path / "world-state.sqlite3")
    module = load_module("health_refresh_composite", "config/windmill/scripts/health/refresh-composite.py")

    result = module.main(repo_path=str(repo_root), dsn=dsn, world_state_dsn=dsn, publish_nats=False)

    assert result["status"] == "ok"
    assert result["entries"][0]["service_id"] == "netbox"
    assert result["entries"][0]["composite_status"] == "critical"
