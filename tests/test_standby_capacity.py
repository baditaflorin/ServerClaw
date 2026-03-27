from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import capacity_report  # noqa: E402
import standby_capacity  # noqa: E402


def write_inventory(path: Path, guest_names: list[str]) -> Path:
    guests = "\n".join(
        f"        {guest_name}:\n          ansible_host: 10.10.10.{index + 10}"
        for index, guest_name in enumerate(guest_names)
    )
    path.write_text(
        (
            "all:\n"
            "  children:\n"
            "    proxmox_hosts:\n"
            "      hosts:\n"
            "        proxmox_florin:\n"
            "          ansible_host: 65.108.75.123\n"
            "    lv3_guests:\n"
            "      hosts:\n"
            f"{guests}\n"
        ),
        encoding="utf-8",
    )
    return path


def write_capacity_model(path: Path, *, host: dict, guests: list[dict], reservations: list[dict]) -> Path:
    path.write_text(
        json.dumps(
            {
                "$schema": "docs/schema/capacity-model.schema.json",
                "schema_version": "1.0.0",
                "host": host,
                "guests": guests,
                "reservations": reservations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def base_host() -> dict:
    return {
        "id": "proxmox_florin",
        "name": "florin",
        "metrics_host": "proxmox_florin",
        "physical": {"ram_gb": 64, "vcpu": 16, "disk_gb": 1000},
        "target_utilisation": {"ram_percent": 80, "vcpu_percent": 75, "disk_percent": 75},
        "reserved_for_platform": {"ram_gb": 8, "vcpu": 2, "disk_gb": 100},
    }


def postgres_service() -> dict:
    return {
        "id": "postgres",
        "name": "PostgreSQL",
        "description": "HA database",
        "category": "data",
        "lifecycle_status": "active",
        "vm": "postgres-lv3",
        "vmid": 150,
        "internal_url": "postgres://database.lv3.org:5432",
        "exposure": "private-only",
        "environments": {
            "production": {
                "status": "active",
                "url": "postgres://database.lv3.org:5432",
            }
        },
        "redundancy": {
            "tier": "R2",
            "rto_target": "5m",
            "rpo_target": "0s",
            "backup_source": "backup_pbs",
            "standby_location": "postgres-replica-lv3",
            "failover_trigger": "Patroni unhealthy",
            "failback_method": "Reinitialize the former primary",
            "standby": {
                "mode": "warm",
                "vm": "postgres-replica-lv3",
                "vmid": 151,
                "reservation": {
                    "resources": {"ram_gb": 8, "vcpu": 4, "disk_gb": 96},
                    "storage_class": "local-lvm",
                    "required_network_attachment": "vmbr10",
                },
                "placement": {
                    "primary_compose_project": "systemd:patroni-postgres-lv3",
                    "standby_compose_project": "systemd:patroni-postgres-replica-lv3",
                    "primary_namespace": "guest:postgres-lv3:patroni",
                    "standby_namespace": "guest:postgres-replica-lv3:patroni",
                    "primary_data_paths": ["guest:postgres-lv3:/var/lib/postgresql"],
                    "standby_data_paths": ["guest:postgres-replica-lv3:/var/lib/postgresql"],
                },
                "failure_domain_honesty": "This warm standby does not cover loss of the single Proxmox host.",
            },
        },
    }


def test_guest_backed_standby_is_approved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        capacity_report,
        "INVENTORY_PATH",
        write_inventory(tmp_path / "hosts.yml", ["postgres-lv3", "postgres-replica-lv3"]),
    )
    model_path = write_capacity_model(
        tmp_path / "capacity-model.json",
        host=base_host(),
        guests=[
            {
                "vmid": 150,
                "name": "postgres-lv3",
                "status": "active",
                "environment": "production",
                "metrics_host": "postgres-lv3",
                "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 96},
                "budget": {"ram_gb": 12, "vcpu": 6, "disk_gb": 128},
                "disk_paths": ["/"],
            },
            {
                "vmid": 151,
                "name": "postgres-replica-lv3",
                "status": "planned",
                "environment": "production",
                "metrics_host": "postgres-replica-lv3",
                "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 96},
                "budget": {"ram_gb": 12, "vcpu": 6, "disk_gb": 128},
                "disk_paths": ["/"],
            },
        ],
        reservations=[],
    )

    verdict = standby_capacity.evaluate_service_standby(
        "postgres",
        catalog={"services": [postgres_service()]},
        model=capacity_report.load_capacity_model(model_path),
    )

    assert verdict["approved"] is True
    assert verdict["backing_source"]["type"] == "guest_budget"


def test_standby_rejects_namespace_and_data_path_conflicts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        capacity_report,
        "INVENTORY_PATH",
        write_inventory(tmp_path / "hosts.yml", ["postgres-lv3"]),
    )
    service = postgres_service()
    service["redundancy"]["standby"]["placement"]["standby_namespace"] = "guest:postgres-lv3:patroni"
    service["redundancy"]["standby"]["placement"]["standby_data_paths"] = [
        "guest:postgres-lv3:/var/lib/postgresql"
    ]
    model_path = write_capacity_model(
        tmp_path / "capacity-model.json",
        host=base_host(),
        guests=[
            {
                "vmid": 150,
                "name": "postgres-lv3",
                "status": "active",
                "environment": "production",
                "metrics_host": "postgres-lv3",
                "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 96},
                "budget": {"ram_gb": 12, "vcpu": 6, "disk_gb": 128},
                "disk_paths": ["/"],
            }
        ],
        reservations=[
            {
                "id": "postgres-standby",
                "kind": "standby",
                "status": "reserved",
                "service_id": "postgres",
                "standby_vm": "postgres-replica-lv3",
                "standby_vmid": 151,
                "storage_class": "local-lvm",
                "required_network_attachment": "vmbr10",
                "reserved": {"ram_gb": 8, "vcpu": 4, "disk_gb": 96},
            }
        ],
    )

    verdict = standby_capacity.evaluate_service_standby(
        "postgres",
        catalog={"services": [service]},
        model=capacity_report.load_capacity_model(model_path),
    )

    assert verdict["approved"] is False
    assert any("share namespace" in reason for reason in verdict["reasons"])
    assert any("share data paths" in reason for reason in verdict["reasons"])


def test_standby_rejects_overcommitted_simulated_load(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        capacity_report,
        "INVENTORY_PATH",
        write_inventory(tmp_path / "hosts.yml", ["docker-runtime-lv3", "postgres-lv3", "postgres-replica-lv3"]),
    )
    model_path = write_capacity_model(
        tmp_path / "capacity-model.json",
        host=base_host(),
        guests=[
            {
                "vmid": 120,
                "name": "docker-runtime-lv3",
                "status": "active",
                "environment": "production",
                "metrics_host": "docker-runtime-lv3",
                "allocated": {"ram_gb": 30, "vcpu": 9, "disk_gb": 590},
                "budget": {"ram_gb": 32, "vcpu": 10, "disk_gb": 620},
                "disk_paths": ["/"],
            },
            {
                "vmid": 150,
                "name": "postgres-lv3",
                "status": "active",
                "environment": "production",
                "metrics_host": "postgres-lv3",
                "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 96},
                "budget": {"ram_gb": 12, "vcpu": 6, "disk_gb": 128},
                "disk_paths": ["/"],
            },
            {
                "vmid": 151,
                "name": "postgres-replica-lv3",
                "status": "planned",
                "environment": "production",
                "metrics_host": "postgres-replica-lv3",
                "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 96},
                "budget": {"ram_gb": 12, "vcpu": 6, "disk_gb": 128},
                "disk_paths": ["/"],
            },
        ],
        reservations=[
            {
                "id": "future-control-plane-standby",
                "kind": "standby",
                "status": "reserved",
                "service_id": "ops_portal",
                "standby_vm": "backup-lv3",
                "storage_class": "local-lvm",
                "required_network_attachment": "vmbr10",
                "reserved": {"ram_gb": 8, "vcpu": 2, "disk_gb": 220},
            }
        ],
    )

    verdict = standby_capacity.evaluate_service_standby(
        "postgres",
        catalog={"services": [postgres_service()]},
        model=capacity_report.load_capacity_model(model_path),
        enforce_capacity_target=True,
    )

    assert verdict["approved"] is False
    assert any("projected standby-aware RAM commitment" in reason for reason in verdict["reasons"])
    assert any("projected standby-aware vCPU commitment" in reason for reason in verdict["reasons"])
    assert any("projected standby-aware disk commitment" in reason for reason in verdict["reasons"])
