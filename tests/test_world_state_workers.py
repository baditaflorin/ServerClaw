from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from platform.world_state.materializer import current_view_rows
from platform.world_state.workers import collect_dns_records, collect_openbao_secret_expiry, run_worker


REPO_ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def sqlite_connection_factory(path: Path):
    def factory() -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    return factory


def prepare_sqlite_world_state(path: Path) -> Path:
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
    connection.commit()
    connection.close()
    return path


@pytest.fixture()
def worker_repo(tmp_path: Path) -> Path:
    write(
        tmp_path / "config" / "subdomain-catalog.json",
        json.dumps(
            {
                "subdomains": [
                    {
                        "fqdn": "grafana.lv3.org",
                        "service_id": "grafana",
                        "environment": "production",
                        "status": "active",
                        "target": "65.108.75.123",
                        "target_port": 443,
                        "exposure": "edge-published",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "secret-catalog.json",
        json.dumps(
            {
                "secrets": [
                    {
                        "id": "windmill_superadmin_secret",
                        "owner_service": "windmill",
                        "rotation_mode": "repo_automated",
                        "rotation_period_days": 30,
                        "last_rotated_at": "2026-03-22",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps(
            {
                "services": [
                    {
                        "id": "grafana",
                        "lifecycle_status": "active",
                        "internal_url": "http://127.0.0.1:65534/health",
                        "vm": "monitoring-lv3",
                        "vmid": 140,
                        "environments": {"production": {"status": "active", "url": "http://127.0.0.1:65534/health"}},
                    }
                ]
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "versions" / "stack.yaml",
        """
observed_state:
  guests:
    instances:
      - vmid: 120
        name: docker-runtime-lv3
        ipv4: 10.10.10.20
        running: true
""".strip()
        + "\n",
    )
    write(
        tmp_path / "inventory" / "hosts.yml",
        """
all:
  children:
    proxmox_hosts:
      hosts:
        proxmox_florin:
          ansible_host: 100.118.189.95
    lv3_guests:
      hosts:
        docker-runtime-lv3:
          ansible_host: 10.10.10.20
          environment: production
""".strip()
        + "\n",
    )
    write(
        tmp_path / "scripts" / "maintenance_window_tool.py",
        """
def list_active_windows():
    return {"maintenance/grafana": {"service_id": "grafana", "reason": "deploy"}}
""".strip()
        + "\n",
    )
    return tmp_path


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_worker_materializes_fixture_surface(worker_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture_path = tmp_path / "proxmox-fixture.json"
    fixture_path.write_text(json.dumps([{"vmid": 110, "name": "nginx-lv3", "status": "running"}]) + "\n")
    monkeypatch.setenv("WORLD_STATE_PROXMOX_VMS_FIXTURE", str(fixture_path))
    db_path = prepare_sqlite_world_state(tmp_path / "world-state.sqlite3")

    result = run_worker(
        "proxmox_vms",
        repo_path=worker_repo,
        publish_nats=False,
        connection_factory=sqlite_connection_factory(db_path),
    )

    assert result["status"] == "ok"
    rows = current_view_rows(connection_factory=sqlite_connection_factory(db_path))
    assert rows[0]["surface"] == "proxmox_vms"
    assert rows[0]["data"][0]["name"] == "nginx-lv3"


def test_collect_dns_records_reads_repo_catalog(worker_repo: Path) -> None:
    records = collect_dns_records(worker_repo)
    assert records == [
        {
            "fqdn": "grafana.lv3.org",
            "service_id": "grafana",
            "environment": "production",
            "status": "active",
            "target": "65.108.75.123",
            "target_port": 443,
            "exposure": "edge-published",
        }
    ]


def test_collect_openbao_secret_expiry_uses_repo_metadata(worker_repo: Path) -> None:
    payload = collect_openbao_secret_expiry(worker_repo)
    assert payload["summary"]["total"] == 1
    assert payload["leases"][0]["secret_id"] == "windmill_superadmin_secret"


def test_worker_script_wrapper_delegates_to_run_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module(
        "refresh_dns_records",
        "config/windmill/scripts/world-state/refresh-dns-records.py",
    )
    captured: dict[str, object] = {}

    def fake_run_worker(surface: str, **kwargs):
        captured["surface"] = surface
        captured["kwargs"] = kwargs
        return {"status": "ok"}

    monkeypatch.setattr(module, "run_worker", fake_run_worker)

    result = module.main(repo_path="/tmp/repo", dsn="sqlite:////tmp/world-state.sqlite", publish_nats=False)

    assert result == {"status": "ok"}
    assert captured["surface"] == "dns_records"
    assert captured["kwargs"] == {
        "repo_path": "/tmp/repo",
        "dsn": "sqlite:////tmp/world-state.sqlite",
        "publish_nats": False,
    }
