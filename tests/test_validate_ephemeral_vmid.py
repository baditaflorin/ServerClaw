from __future__ import annotations

import json
from pathlib import Path

import pytest

import validate_ephemeral_vmid


@pytest.fixture()
def validation_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "inventory" / "host_vars").mkdir(parents=True)
    (tmp_path / "versions").mkdir()

    (tmp_path / "config" / "capacity-model.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "reservations": [
                    {
                        "id": "ephemeral-pool",
                        "kind": "ephemeral_pool",
                        "status": "reserved",
                        "vmid_range": {"start": 910, "end": 979},
                        "max_concurrent_vms": 5,
                        "reserved": {"ram_gb": 20, "vcpu": 8, "disk_gb": 100},
                        "notes": "test pool",
                    }
                ],
            }
        )
        + "\n"
    )
    (tmp_path / "inventory" / "host_vars" / "proxmox-host.yml").write_text(
        "proxmox_guests:\n  - vmid: 110\n    name: nginx-edge\n"
    )
    (tmp_path / "versions" / "stack.yaml").write_text(
        "\n".join(
            [
                "observed_state:",
                "  guests:",
                "    template:",
                "      vmid: 9000",
                "    instances:",
                "      - vmid: 110",
                "        name: nginx-edge",
                "desired_state:",
                "  guest_provisioning:",
                "    guest_vmids:",
                "      nginx_vm: 110",
            ]
        )
        + "\n"
    )

    monkeypatch.setattr(validate_ephemeral_vmid, "CAPACITY_MODEL_PATH", tmp_path / "config" / "capacity-model.json")
    # ADR 0430 — host_vars reads go through load_topology_host_vars (overlay-aware).
    # Point the test fixture through that loader instead of a path constant.
    fixture_path = tmp_path / "inventory" / "host_vars" / "proxmox-host.yml"
    monkeypatch.setattr(
        validate_ephemeral_vmid,
        "load_topology_host_vars",
        lambda: __import__("yaml").safe_load(fixture_path.read_text()),
    )
    monkeypatch.setattr(validate_ephemeral_vmid, "STACK_PATH", tmp_path / "versions" / "stack.yaml")
    return tmp_path


def test_validation_passes_when_managed_vmids_are_outside_ephemeral_range(validation_repo: Path) -> None:
    assert validate_ephemeral_vmid.validate_ephemeral_vmid_ranges() == []


def test_validation_detects_overlap_in_inventory(validation_repo: Path) -> None:
    (validation_repo / "inventory" / "host_vars" / "proxmox-host.yml").write_text(
        "proxmox_guests:\n  - vmid: 910\n    name: overlap\n"
    )

    violations = validate_ephemeral_vmid.validate_ephemeral_vmid_ranges()

    assert violations == ["inventory guest overlap uses reserved ephemeral VMID 910"]


def test_validation_ignores_alias_inventory_entries(validation_repo: Path) -> None:
    (validation_repo / "inventory" / "host_vars" / "proxmox-host.yml").write_text(
        "\n".join(
            [
                "proxmox_guests:",
                "  - vmid: 910",
                "    name: docker-runtime",
                "    tags:",
                "      - alias",
            ]
        )
        + "\n"
    )

    assert validate_ephemeral_vmid.validate_ephemeral_vmid_ranges() == []
