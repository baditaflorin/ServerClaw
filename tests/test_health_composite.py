from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import platform.health.composite as composite_module
from platform.health import HealthCompositeClient, compute_health_entries


def test_compute_health_entries_detects_failure_modes() -> None:
    services = [
        {"id": "netbox", "lifecycle_status": "active"},
        {"id": "grafana", "lifecycle_status": "active"},
        {"id": "keycloak", "lifecycle_status": "active"},
    ]

    entries = compute_health_entries(
        services,
        service_health_snapshot={
            "services": [
                {"service_id": "netbox", "status": "down"},
                {"service_id": "grafana", "status": "healthy"},
                {"service_id": "keycloak", "status": "down"},
            ]
        },
        slo_entries=[],
        drift_report={"records": [{"service": "grafana", "severity": "critical"}]},
        triage_reports=[{"incident_id": "inc-1", "affected_service": "netbox", "status": "firing"}],
        maintenance_windows=[{"service_id": "keycloak", "starts_at": "2026-03-24T10:00:00Z"}],
        ledger_events=[],
        computed_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
    )
    by_service = {entry.service_id: entry for entry in entries}

    assert by_service["netbox"].composite_status == "critical"
    assert by_service["netbox"].safe_to_act is False
    assert by_service["grafana"].composite_status == "degraded"
    assert by_service["grafana"].safe_to_act is False
    assert by_service["keycloak"].composite_status == "maintenance"
    assert by_service["keycloak"].safe_to_act is True


def test_health_client_refresh_persists_sqlite_entries(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "config").mkdir()
    (repo_root / "versions").mkdir()
    (repo_root / "config" / "service-capability-catalog.json").write_text(
        json.dumps({"services": [{"id": "netbox", "name": "NetBox", "lifecycle_status": "active"}]}) + "\n",
        encoding="utf-8",
    )
    (repo_root / "versions" / "stack.yaml").write_text("repo_version: 0.1.0\nplatform_version: 0.1.0\n", encoding="utf-8")

    db_path = tmp_path / "health.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE world_state_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, surface TEXT NOT NULL, collected_at TEXT NOT NULL, data TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0)"
    )
    connection.execute(
        "CREATE TABLE world_state_current_view (surface TEXT PRIMARY KEY, data TEXT NOT NULL, collected_at TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0, is_expired INTEGER NOT NULL DEFAULT 0)"
    )
    connection.execute(
        "INSERT INTO world_state_current_view (surface, data, collected_at, stale, is_expired) VALUES (?, ?, ?, ?, ?)",
        (
            "service_health",
            json.dumps({"services": [{"service_id": "netbox", "status": "degraded"}]}),
            "2026-03-24T10:00:00+00:00",
            0,
            0,
        ),
    )
    connection.commit()
    connection.close()

    client = HealthCompositeClient(
        repo_root=repo_root,
        dsn=f"sqlite:///{db_path}",
        world_state_dsn=f"sqlite:///{db_path}",
    )
    result = client.refresh(allow_live_slo_queries=False)

    assert result["status"] == "ok"
    entry = client.get("netbox", allow_stale=True)
    assert entry.composite_status == "degraded"
    assert entry.composite_score == 0.8

def test_compute_health_entries_marks_active_degradation_as_degraded() -> None:
    entries = compute_health_entries(
        [{"id": "api_gateway", "lifecycle_status": "active"}],
        service_health_snapshot={"services": [{"service_id": "api_gateway", "status": "healthy"}]},
        slo_entries=[],
        drift_report={},
        triage_reports=[],
        maintenance_windows=[],
        ledger_events=[],
        degradation_state={
            "api_gateway": [
                {
                    "dependency": "keycloak",
                    "degraded_behaviour": "Use cached JWKS while Keycloak is unavailable.",
                }
            ]
        },
        computed_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
    )

    assert entries[0].composite_status == "degraded"
    assert entries[0].safe_to_act is False
    assert any(signal.name == "degraded_mode" for signal in entries[0].signals)


def test_compute_health_entries_treats_startup_runtime_state_as_non_critical() -> None:
    entries = compute_health_entries(
        [{"id": "api_gateway", "lifecycle_status": "active"}],
        service_health_snapshot={"services": [{"service_id": "api_gateway", "status": "starting", "runtime_state": "startup"}]},
        slo_entries=[],
        drift_report={},
        triage_reports=[],
        maintenance_windows=[],
        ledger_events=[],
        computed_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
    )

    assert entries[0].composite_status == "degraded"
    assert entries[0].signals[0].value == "startup"
    assert entries[0].signals[0].reason == "service is still starting"


def test_load_maintenance_windows_skips_missing_script_dependencies(monkeypatch: object, tmp_path: Path) -> None:
    class FakeWorldStateClient:
        def get(self, *_args: object, **_kwargs: object) -> None:
            return None

    def fail_windows(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("missing maintenance dependency")

    monkeypatch.setattr(composite_module, "list_active_windows_best_effort", fail_windows)

    assert composite_module.load_maintenance_windows(tmp_path, world_state=FakeWorldStateClient()) == []


def test_load_slo_entries_skips_missing_script_dependencies(monkeypatch: object, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "slo-catalog.json").write_text('{"schema_version":"1.0.0","slos":[]}', encoding="utf-8")

    def fail_slo(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("missing slo dependency")

    monkeypatch.setattr(composite_module, "build_slo_status_entries", fail_slo)

    assert composite_module.load_slo_entries(tmp_path, allow_live_queries=False) == []
