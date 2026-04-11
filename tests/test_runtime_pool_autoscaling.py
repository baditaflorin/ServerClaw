from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import runtime_pool_autoscaling  # noqa: E402


def test_repo_runtime_pool_autoscaling_catalog_loads() -> None:
    catalog = runtime_pool_autoscaling.load_runtime_pool_autoscaling()

    assert catalog.controller.preferred_implementation == "nomad-autoscaler"
    assert catalog.controller.metrics_source == "prometheus"
    assert catalog.controller.routing_surface == "traefik"
    assert catalog.controller.invocation_surface == "dapr"
    assert [policy.pool_id for policy in catalog.policies] == ["runtime-general", "runtime-ai"]


def test_runtime_pool_autoscaling_rejects_runtime_control_policy_in_first_phase(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "inventory" / "hosts.yml"
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(
        """
all:
  children:
    proxmox_hosts:
      hosts:
        proxmox-host:
          ansible_host: 203.0.113.1
    lv3_guests:
      hosts: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    service_catalog_path = tmp_path / "config" / "service-capability-catalog.json"
    service_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    service_catalog_path.write_text(
        json.dumps(
            {
                "$schema": "docs/schema/service-capability-catalog.schema.json",
                "schema_version": "1.0.0",
                "services": [
                    {"id": "keycloak", "runtime_pool": "runtime-control", "mobility_tier": "anchor"},
                    {"id": "homepage", "runtime_pool": "runtime-general", "mobility_tier": "elastic_stateless"},
                    {"id": "tika", "runtime_pool": "runtime-ai", "mobility_tier": "burst_batch"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    execution_lanes_path = tmp_path / "config" / "execution-lanes.yaml"
    execution_lanes_path.write_text(
        """
schema_version: 1.0.0
lanes:
  - lane_id: lane:runtime-general
  - lane_id: lane:runtime-ai
  - lane_id: lane:docker-runtime
""".strip()
        + "\n",
        encoding="utf-8",
    )

    receipts_dir = tmp_path / "receipts" / "runtime-pool-scaling"
    receipts_dir.mkdir(parents=True)

    capacity_model_path = tmp_path / "config" / "capacity-model.json"
    capacity_model_path.write_text(
        json.dumps(
            {
                "$schema": "docs/schema/capacity-model.schema.json",
                "schema_version": "1.0.0",
                "host": {
                    "id": "proxmox-host",
                    "name": "florin",
                    "metrics_host": "proxmox-host",
                    "physical": {"ram_gb": 128, "vcpu": 32, "disk_gb": 1000},
                    "target_utilisation": {
                        "ram_percent": 80,
                        "vcpu_percent": 75,
                        "disk_percent": 75,
                    },
                    "reserved_for_platform": {"ram_gb": 8, "vcpu": 2, "disk_gb": 100},
                },
                "guests": [],
                "runtime_pool_memory": {
                    "host_free_memory_floor_gb": 20,
                    "measurement_and_control": {
                        "metrics_source": "prometheus",
                        "control_surface": "nomad-autoscaler",
                    },
                    "pools": [
                        {"id": "runtime-control", "baseline_ram_gb": 12, "max_ram_gb": 16, "admission_priority": 1},
                        {"id": "runtime-general", "baseline_ram_gb": 12, "max_ram_gb": 20, "admission_priority": 2},
                        {"id": "runtime-ai", "baseline_ram_gb": 16, "max_ram_gb": 28, "admission_priority": 3},
                    ],
                },
                "reservations": [],
                "service_load_profiles": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    autoscaling_config_path = tmp_path / "config" / "runtime-pool-autoscaling.json"
    autoscaling_config_path.write_text(
        json.dumps(
            {
                "$schema": "docs/schema/runtime-pool-autoscaling.schema.json",
                "schema_version": "1.0.0",
                "controller": {
                    "preferred_implementation": "nomad-autoscaler",
                    "metrics_source": "prometheus",
                    "routing_surface": "traefik",
                    "invocation_surface": "dapr",
                    "receipt_directory": str(receipts_dir.relative_to(tmp_path)),
                    "pause_conditions": ["active_deploy", "active_migration"],
                },
                "policies": [
                    {
                        "pool_id": "runtime-control",
                        "enabled": True,
                        "nomad_namespace": "runtime-control",
                        "instance_bounds": {"min": 1, "max": 1},
                        "scale_out": {
                            "working_set_utilization_percent": 75,
                            "sustain_minutes": 10,
                            "oom_event_immediate": True,
                        },
                        "scale_in": {
                            "working_set_utilization_percent": 55,
                            "cooldown_minutes": 60,
                        },
                        "required_signals": [
                            "available_memory_percent",
                            "memory_pressure_stall",
                            "swap_activity",
                            "oom_or_restart_evidence",
                        ],
                        "allowed_mobility_tiers": ["elastic_stateless", "burst_batch"],
                        "pause_when_lanes_active": ["lane:docker-runtime"],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    original_repo_root = runtime_pool_autoscaling.REPO_ROOT
    try:
        runtime_pool_autoscaling.REPO_ROOT = tmp_path
        with pytest.raises(ValueError, match="must be runtime-general or runtime-ai"):
            runtime_pool_autoscaling.load_runtime_pool_autoscaling(
                autoscaling_config_path,
                capacity_model_path=capacity_model_path,
                service_catalog_path=service_catalog_path,
                inventory_path=inventory_path,
                execution_lanes_path=execution_lanes_path,
            )
    finally:
        runtime_pool_autoscaling.REPO_ROOT = original_repo_root
