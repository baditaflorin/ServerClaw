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
    fixture_receipts = tmp_path / "receipts" / "fixtures"
    fixture_receipts.mkdir(parents=True)
    monkeypatch.setattr(capacity_report, "FIXTURE_RECEIPTS_DIR", fixture_receipts)

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
                    {
                        "vmid": 151,
                        "name": "postgres-replica-lv3",
                        "status": "planned",
                        "environment": "production",
                        "metrics_host": "postgres-replica-lv3",
                        "allocated": {"ram_gb": 8, "vcpu": 4, "disk_gb": 96},
                        "budget": {"ram_gb": 12, "vcpu": 6, "disk_gb": 128},
                        "capacity_class": "ha_reserved",
                        "disk_paths": ["/"],
                    },
                ],
                "reservations": [
                    {
                        "id": "ephemeral-pool",
                        "kind": "ephemeral_pool",
                        "status": "reserved",
                        "capacity_class": "preview_burst",
                        "vmid_range": {"start": 910, "end": 979},
                        "max_concurrent_vms": 5,
                        "reserved": {"ram_gb": 8, "vcpu": 4, "disk_gb": 40},
                    },
                    {
                        "id": "recovery-drill-pool",
                        "kind": "planned_growth",
                        "status": "reserved",
                        "capacity_class": "recovery_reserved",
                        "reserved": {"ram_gb": 4, "vcpu": 2, "disk_gb": 48},
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


def test_capacity_model_accepts_service_load_profiles(capacity_fixture: Path) -> None:
    payload = json.loads(capacity_fixture.read_text(encoding="utf-8"))
    payload["service_load_profiles"] = [
        {
            "service_id": "nginx_edge",
            "typical_concurrency": 5,
            "smoke_vus": 2,
            "request_timeout_seconds": 10,
            "think_time_seconds": 0.5,
        }
    ]
    capacity_fixture.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    model = capacity_report.load_capacity_model(capacity_fixture)

    assert model.host.identifier == "proxmox_florin"


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


def test_capacity_class_request_allows_declared_recovery_drill_to_borrow_preview(
    capacity_fixture: Path,
) -> None:
    model = capacity_report.load_capacity_model(capacity_fixture)

    verdict = capacity_report.check_capacity_class_request(
        model,
        requester_class="restore-verification",
        requested=capacity_report.ResourceAmount(ram_gb=6, vcpu=3, disk_gb=50),
        declared_drill=True,
    )

    assert verdict["approved"] is True
    assert verdict["borrowed_from"] == ["preview_burst"]


def test_capacity_class_request_rejects_preview_without_break_glass(
    capacity_fixture: Path,
) -> None:
    model = capacity_report.load_capacity_model(capacity_fixture)

    verdict = capacity_report.check_capacity_class_request(
        model,
        requester_class="preview",
        requested=capacity_report.ResourceAmount(ram_gb=12, vcpu=5, disk_gb=60),
    )

    assert verdict["approved"] is False
    assert any("break-glass" in reason for reason in verdict["reasons"])


def test_report_json_includes_capacity_class_occupancy_from_active_fixture_receipts(
    capacity_fixture: Path,
) -> None:
    fixture_receipt = capacity_fixture.parents[1] / "receipts" / "fixtures" / "fixture.json"
    fixture_receipt.write_text(
        json.dumps(
            {
                "status": "active",
                "definition": {
                    "resources": {
                        "memory_mb": 2048,
                        "cores": 2,
                        "disk_gb": 20,
                    }
                },
            }
        )
        + "\n"
    )

    model = capacity_report.load_capacity_model(capacity_fixture)
    report = capacity_report.build_report(model, with_live_metrics=False)
    payload = json.loads(capacity_report.render_json(report))

    preview = next(item for item in payload["capacity_classes"] if item["id"] == "preview_burst")
    assert preview["occupied"] == {"ram_gb": 2, "vcpu": 2.0, "disk_gb": 20.0}
