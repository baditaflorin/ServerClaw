from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import capacity_report  # noqa: E402


@pytest.fixture()
def capacity_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    inventory_path = tmp_path / "inventory" / "hosts.yml"
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(
        """
all:
  children:
    proxmox_hosts:
      hosts:
        proxmox_florin:
          ansible_host: 65.108.75.123
    lv3_guests:
      hosts:
        nginx-lv3:
          ansible_host: 10.10.10.10
        docker-runtime-lv3:
          ansible_host: 10.10.10.20
""".strip()
        + "\n"
    )
    monkeypatch.setattr(capacity_report, "INVENTORY_PATH", inventory_path)

    model_path = tmp_path / "config" / "capacity-model.json"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        json.dumps(
            {
                "$schema": "docs/schema/capacity-model.schema.json",
                "schema_version": "1.0.0",
                "host": {
                    "id": "proxmox_florin",
                    "name": "florin",
                    "metrics_host": "proxmox_florin",
                    "physical": {"ram_gb": 64, "vcpu": 16, "disk_gb": 1000},
                    "target_utilisation": {
                        "ram_percent": 80,
                        "vcpu_percent": 75,
                        "disk_percent": 75,
                    },
                    "reserved_for_platform": {"ram_gb": 8, "vcpu": 2, "disk_gb": 100},
                },
                "guests": [
                    {
                        "vmid": 110,
                        "name": "nginx-lv3",
                        "status": "active",
                        "environment": "production",
                        "metrics_host": "nginx-lv3",
                        "allocated": {"ram_gb": 4, "vcpu": 2, "disk_gb": 32},
                        "budget": {"ram_gb": 6, "vcpu": 4, "disk_gb": 48},
                        "disk_paths": ["/"],
                    },
                    {
                        "vmid": 120,
                        "name": "docker-runtime-lv3",
                        "status": "active",
                        "environment": "production",
                        "metrics_host": "docker-runtime-lv3",
                        "allocated": {"ram_gb": 24, "vcpu": 4, "disk_gb": 96},
                        "budget": {"ram_gb": 32, "vcpu": 8, "disk_gb": 160},
                        "disk_paths": ["/"],
                    },
                ],
                "reservations": [
                    {
                        "id": "ephemeral-pool",
                        "kind": "ephemeral_pool",
                        "status": "reserved",
                        "vmid_range": {"start": 910, "end": 979},
                        "max_concurrent_vms": 5,
                        "reserved": {"ram_gb": 8, "vcpu": 4, "disk_gb": 40},
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return model_path


def test_build_report_without_live_metrics_renders_guest_summary(capacity_fixture: Path) -> None:
    model = capacity_report.load_capacity_model(capacity_fixture)
    report = capacity_report.build_report(model, with_live_metrics=False)

    output = capacity_report.render_text(report)

    assert "Metrics source: disabled" in output
    assert "nginx-lv3 [active]" in output
    assert "actual=n/a" in output


def test_capacity_gate_rejects_projected_overcommit(capacity_fixture: Path) -> None:
    model = capacity_report.load_capacity_model(capacity_fixture)

    approved, reasons = capacity_report.check_capacity_gate(
        model,
        proposed_changes=[capacity_report.ResourceAmount(ram_gb=20, vcpu=10, disk_gb=600)],
    )

    assert not approved
    assert any("RAM" in reason for reason in reasons)
    assert any("vCPU" in reason for reason in reasons)
    assert any("disk" in reason for reason in reasons)


def test_main_check_gate_emits_json_and_failure_code(
    capacity_fixture: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = capacity_report.main(
        [
            "--model",
            str(capacity_fixture),
            "--check-gate",
            "--proposed-change",
            "20,10,600",
        ]
    )
    captured = capsys.readouterr()

    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["approved"] is False
    assert payload["reasons"]
