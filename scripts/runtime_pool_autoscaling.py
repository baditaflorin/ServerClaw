#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller_automation_toolkit import REPO_ROOT, emit_cli_error, load_json, load_yaml

from capacity_report import (
    CAPACITY_MODEL_PATH,
    SERVICE_CATALOG_PATH,
    CapacityModel,
    load_capacity_model,
    require_list,
    require_mapping,
    require_number,
    require_str,
)


AUTOSCALING_CONFIG_PATH = REPO_ROOT / "config" / "runtime-pool-autoscaling.json"
EXECUTION_LANES_PATH = REPO_ROOT / "config" / "execution-lanes.yaml"
INVENTORY_PATH = REPO_ROOT / "inventory" / "hosts.yml"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
REQUIRED_SIGNALS = {
    "available_memory_percent",
    "memory_pressure_stall",
    "swap_activity",
    "oom_or_restart_evidence",
}
ELIGIBLE_MOBILITY_TIERS = {"elastic_stateless", "burst_batch"}


@dataclass(frozen=True)
class AutoscalingController:
    preferred_implementation: str
    metrics_source: str
    routing_surface: str
    invocation_surface: str
    receipt_directory: str
    pause_conditions: tuple[str, ...]


@dataclass(frozen=True)
class InstanceBounds:
    minimum: int
    maximum: int


@dataclass(frozen=True)
class ScaleOutPolicy:
    working_set_utilization_percent: float
    sustain_minutes: int
    oom_event_immediate: bool


@dataclass(frozen=True)
class ScaleInPolicy:
    working_set_utilization_percent: float
    cooldown_minutes: int


@dataclass(frozen=True)
class RuntimePoolAutoscalingPolicy:
    pool_id: str
    enabled: bool
    nomad_namespace: str
    instance_bounds: InstanceBounds
    scale_out: ScaleOutPolicy
    scale_in: ScaleInPolicy
    required_signals: tuple[str, ...]
    allowed_mobility_tiers: tuple[str, ...]
    pause_when_lanes_active: tuple[str, ...]
    notes: str | None = None


@dataclass(frozen=True)
class RuntimePoolAutoscalingCatalog:
    controller: AutoscalingController
    policies: tuple[RuntimePoolAutoscalingPolicy, ...]


def load_execution_lane_ids(path: Path = EXECUTION_LANES_PATH) -> set[str]:
    payload = require_mapping(load_yaml(path), str(path))
    lanes = require_list(payload.get("lanes"), f"{path}.lanes")
    lane_ids: set[str] = set()
    for index, item in enumerate(lanes):
        lane = require_mapping(item, f"{path}.lanes[{index}]")
        lane_ids.add(require_str(lane.get("lane_id"), f"{path}.lanes[{index}].lane_id"))
    return lane_ids


def eligible_service_ids_by_pool(service_catalog_path: Path = SERVICE_CATALOG_PATH) -> dict[str, set[str]]:
    payload = require_mapping(load_json(service_catalog_path), str(service_catalog_path))
    services = require_list(payload.get("services"), f"{service_catalog_path}.services")
    eligible: dict[str, set[str]] = {}
    for index, item in enumerate(services):
        service = require_mapping(item, f"{service_catalog_path}.services[{index}]")
        pool_id = require_str(service.get("runtime_pool"), f"{service_catalog_path}.services[{index}].runtime_pool")
        mobility_tier = require_str(
            service.get("mobility_tier"),
            f"{service_catalog_path}.services[{index}].mobility_tier",
        )
        if mobility_tier not in ELIGIBLE_MOBILITY_TIERS:
            continue
        eligible.setdefault(pool_id, set()).add(
            require_str(service.get("id"), f"{service_catalog_path}.services[{index}].id")
        )
    return eligible


def validate_runtime_pool_autoscaling_payload(
    payload: dict[str, Any],
    *,
    capacity_model: CapacityModel,
    execution_lane_ids: set[str],
    eligible_services: dict[str, set[str]],
) -> None:
    if (
        require_str(payload.get("$schema"), "config/runtime-pool-autoscaling.json.$schema")
        != "docs/schema/runtime-pool-autoscaling.schema.json"
    ):
        raise ValueError(
            "config/runtime-pool-autoscaling.json.$schema must reference docs/schema/runtime-pool-autoscaling.schema.json"
        )
    schema_version = require_str(
        payload.get("schema_version"),
        "config/runtime-pool-autoscaling.json.schema_version",
    )
    if not SEMVER_RE.match(schema_version):
        raise ValueError("config/runtime-pool-autoscaling.json.schema_version must be semver")

    if capacity_model.runtime_pool_memory is None:
        raise ValueError(
            "config/capacity-model.json must define runtime_pool_memory before autoscaling can be validated"
        )
    governed_pool_ids = {pool.identifier for pool in capacity_model.runtime_pool_memory.pools}

    controller = require_mapping(payload.get("controller"), "config/runtime-pool-autoscaling.json.controller")
    preferred_implementation = require_str(
        controller.get("preferred_implementation"),
        "config/runtime-pool-autoscaling.json.controller.preferred_implementation",
    )
    metrics_source = require_str(
        controller.get("metrics_source"),
        "config/runtime-pool-autoscaling.json.controller.metrics_source",
    )
    routing_surface = require_str(
        controller.get("routing_surface"),
        "config/runtime-pool-autoscaling.json.controller.routing_surface",
    )
    invocation_surface = require_str(
        controller.get("invocation_surface"),
        "config/runtime-pool-autoscaling.json.controller.invocation_surface",
    )
    receipt_directory = require_str(
        controller.get("receipt_directory"),
        "config/runtime-pool-autoscaling.json.controller.receipt_directory",
    )
    pause_conditions = {
        require_str(
            item,
            f"config/runtime-pool-autoscaling.json.controller.pause_conditions[{index}]",
        )
        for index, item in enumerate(
            require_list(
                controller.get("pause_conditions"),
                "config/runtime-pool-autoscaling.json.controller.pause_conditions",
            )
        )
    }
    if preferred_implementation != "nomad-autoscaler":
        raise ValueError(
            "config/runtime-pool-autoscaling.json.controller.preferred_implementation must be 'nomad-autoscaler'"
        )
    if metrics_source != "prometheus":
        raise ValueError("config/runtime-pool-autoscaling.json.controller.metrics_source must be 'prometheus'")
    if routing_surface != "traefik":
        raise ValueError("config/runtime-pool-autoscaling.json.controller.routing_surface must be 'traefik'")
    if invocation_surface != "dapr":
        raise ValueError("config/runtime-pool-autoscaling.json.controller.invocation_surface must be 'dapr'")
    if not (REPO_ROOT / receipt_directory).exists():
        raise ValueError(
            "config/runtime-pool-autoscaling.json.controller.receipt_directory must exist in the repository"
        )
    if {"active_deploy", "active_migration"} - pause_conditions:
        raise ValueError(
            "config/runtime-pool-autoscaling.json.controller.pause_conditions must include active_deploy and active_migration"
        )

    policies = require_list(payload.get("policies"), "config/runtime-pool-autoscaling.json.policies")
    seen_pool_ids: set[str] = set()
    for index, item in enumerate(policies):
        policy = require_mapping(item, f"config/runtime-pool-autoscaling.json.policies[{index}]")
        pool_id = require_str(policy.get("pool_id"), f"config/runtime-pool-autoscaling.json.policies[{index}].pool_id")
        if pool_id in seen_pool_ids:
            raise ValueError(f"duplicate autoscaling policy for '{pool_id}'")
        seen_pool_ids.add(pool_id)
        if pool_id not in governed_pool_ids:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}].pool_id references unknown runtime pool '{pool_id}'"
            )
        if pool_id not in {"runtime-general", "runtime-ai"}:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}].pool_id must be runtime-general or runtime-ai in the first autoscaling phase"
            )
        nomad_namespace = require_str(
            policy.get("nomad_namespace"),
            f"config/runtime-pool-autoscaling.json.policies[{index}].nomad_namespace",
        )
        if nomad_namespace != pool_id:
            raise ValueError(
                f"config/runtime-pool-autoscaling.json.policies[{index}].nomad_namespace must match pool_id"
            )
        enabled = policy.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError(f"config/runtime-pool-autoscaling.json.policies[{index}].enabled must be a boolean")
        if not enabled:
            raise ValueError(
                f"config/runtime-pool-autoscaling.json.policies[{index}].enabled must be true for the current rollout"
            )

        instance_bounds = require_mapping(
            policy.get("instance_bounds"),
            f"config/runtime-pool-autoscaling.json.policies[{index}].instance_bounds",
        )
        minimum = int(
            require_number(
                instance_bounds.get("min"),
                f"config/runtime-pool-autoscaling.json.policies[{index}].instance_bounds.min",
                1,
            )
        )
        maximum = int(
            require_number(
                instance_bounds.get("max"),
                f"config/runtime-pool-autoscaling.json.policies[{index}].instance_bounds.max",
                1,
            )
        )
        if minimum < 1 or maximum < 1 or minimum > maximum:
            raise ValueError(
                f"config/runtime-pool-autoscaling.json.policies[{index}].instance_bounds must be ascending positive integers"
            )
        if maximum > 2:
            raise ValueError(
                f"config/runtime-pool-autoscaling.json.policies[{index}].instance_bounds.max must be <= 2 in the first autoscaling phase"
            )

        scale_out = require_mapping(
            policy.get("scale_out"),
            f"config/runtime-pool-autoscaling.json.policies[{index}].scale_out",
        )
        scale_out_threshold = require_number(
            scale_out.get("working_set_utilization_percent"),
            f"config/runtime-pool-autoscaling.json.policies[{index}].scale_out.working_set_utilization_percent",
            1,
        )
        scale_out_minutes = int(
            require_number(
                scale_out.get("sustain_minutes"),
                f"config/runtime-pool-autoscaling.json.policies[{index}].scale_out.sustain_minutes",
                1,
            )
        )
        oom_event_immediate = scale_out.get("oom_event_immediate")
        if not isinstance(oom_event_immediate, bool):
            raise ValueError(
                f"config/runtime-pool-autoscaling.json.policies[{index}].scale_out.oom_event_immediate must be a boolean"
            )

        scale_in = require_mapping(
            policy.get("scale_in"),
            f"config/runtime-pool-autoscaling.json.policies[{index}].scale_in",
        )
        scale_in_threshold = require_number(
            scale_in.get("working_set_utilization_percent"),
            f"config/runtime-pool-autoscaling.json.policies[{index}].scale_in.working_set_utilization_percent",
            1,
        )
        cooldown_minutes = int(
            require_number(
                scale_in.get("cooldown_minutes"),
                f"config/runtime-pool-autoscaling.json.policies[{index}].scale_in.cooldown_minutes",
                1,
            )
        )

        if scale_out_threshold <= scale_in_threshold:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}] scale_out threshold must be greater than scale_in threshold"
            )
        if scale_out_threshold != 75 or scale_out_minutes != 10:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}] must use the governed default scale-out threshold of 75% for 10 minutes"
            )
        if scale_in_threshold != 55 or cooldown_minutes != 60:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}] must use the governed default scale-in threshold of 55% for 60 minutes"
            )

        required_signals = {
            require_str(
                item,
                f"config/runtime-pool-autoscaling.json.policies[{index}].required_signals[{signal_index}]",
            )
            for signal_index, item in enumerate(
                require_list(
                    policy.get("required_signals"),
                    f"config/runtime-pool-autoscaling.json.policies[{index}].required_signals",
                )
            )
        }
        if REQUIRED_SIGNALS - required_signals:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}].required_signals must include {sorted(REQUIRED_SIGNALS)}"
            )

        allowed_mobility_tiers = {
            require_str(
                item,
                f"config/runtime-pool-autoscaling.json.policies[{index}].allowed_mobility_tiers[{tier_index}]",
            )
            for tier_index, item in enumerate(
                require_list(
                    policy.get("allowed_mobility_tiers"),
                    f"config/runtime-pool-autoscaling.json.policies[{index}].allowed_mobility_tiers",
                )
            )
        }
        if not allowed_mobility_tiers:
            raise ValueError(
                f"config/runtime-pool-autoscaling.json.policies[{index}].allowed_mobility_tiers must not be empty"
            )
        if allowed_mobility_tiers - ELIGIBLE_MOBILITY_TIERS:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}].allowed_mobility_tiers must be limited to {sorted(ELIGIBLE_MOBILITY_TIERS)}"
            )

        pause_when_lanes_active = {
            require_str(
                item,
                f"config/runtime-pool-autoscaling.json.policies[{index}].pause_when_lanes_active[{lane_index}]",
            )
            for lane_index, item in enumerate(
                require_list(
                    policy.get("pause_when_lanes_active"),
                    f"config/runtime-pool-autoscaling.json.policies[{index}].pause_when_lanes_active",
                )
            )
        }
        expected_lane = f"lane:{pool_id}"
        if expected_lane not in pause_when_lanes_active:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}].pause_when_lanes_active must include '{expected_lane}'"
            )
        missing_lanes = pause_when_lanes_active - execution_lane_ids
        if missing_lanes:
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}].pause_when_lanes_active references unknown lanes {sorted(missing_lanes)}"
            )

        if not eligible_services.get(pool_id):
            raise ValueError(
                "config/runtime-pool-autoscaling.json.policies["
                f"{index}] has no elastic or burst services in the service catalog for pool '{pool_id}'"
            )
        if "notes" in policy:
            require_str(
                policy.get("notes"),
                f"config/runtime-pool-autoscaling.json.policies[{index}].notes",
            )

    if seen_pool_ids != {"runtime-general", "runtime-ai"}:
        raise ValueError(
            "config/runtime-pool-autoscaling.json.policies must define exactly runtime-general and runtime-ai in the first autoscaling phase"
        )


def load_runtime_pool_autoscaling(
    path: Path = AUTOSCALING_CONFIG_PATH,
    *,
    capacity_model_path: Path = CAPACITY_MODEL_PATH,
    service_catalog_path: Path = SERVICE_CATALOG_PATH,
    inventory_path: Path = INVENTORY_PATH,
    execution_lanes_path: Path = EXECUTION_LANES_PATH,
) -> RuntimePoolAutoscalingCatalog:
    payload = require_mapping(load_json(path), str(path))
    capacity_model = load_capacity_model(
        capacity_model_path,
        service_catalog_path=service_catalog_path,
        inventory_path=inventory_path,
    )
    execution_lane_ids = load_execution_lane_ids(execution_lanes_path)
    eligible_services = eligible_service_ids_by_pool(service_catalog_path)
    validate_runtime_pool_autoscaling_payload(
        payload,
        capacity_model=capacity_model,
        execution_lane_ids=execution_lane_ids,
        eligible_services=eligible_services,
    )

    controller_payload = require_mapping(payload.get("controller"), f"{path}.controller")
    policies_payload = require_list(payload.get("policies"), f"{path}.policies")
    controller = AutoscalingController(
        preferred_implementation=require_str(
            controller_payload.get("preferred_implementation"),
            f"{path}.controller.preferred_implementation",
        ),
        metrics_source=require_str(controller_payload.get("metrics_source"), f"{path}.controller.metrics_source"),
        routing_surface=require_str(controller_payload.get("routing_surface"), f"{path}.controller.routing_surface"),
        invocation_surface=require_str(
            controller_payload.get("invocation_surface"),
            f"{path}.controller.invocation_surface",
        ),
        receipt_directory=require_str(
            controller_payload.get("receipt_directory"),
            f"{path}.controller.receipt_directory",
        ),
        pause_conditions=tuple(
            require_str(item, f"{path}.controller.pause_conditions[{index}]")
            for index, item in enumerate(
                require_list(
                    controller_payload.get("pause_conditions"),
                    f"{path}.controller.pause_conditions",
                )
            )
        ),
    )
    policies = []
    for index, item in enumerate(policies_payload):
        policy = require_mapping(item, f"{path}.policies[{index}]")
        bounds = require_mapping(policy.get("instance_bounds"), f"{path}.policies[{index}].instance_bounds")
        scale_out = require_mapping(policy.get("scale_out"), f"{path}.policies[{index}].scale_out")
        scale_in = require_mapping(policy.get("scale_in"), f"{path}.policies[{index}].scale_in")
        policies.append(
            RuntimePoolAutoscalingPolicy(
                pool_id=require_str(policy.get("pool_id"), f"{path}.policies[{index}].pool_id"),
                enabled=bool(policy.get("enabled")),
                nomad_namespace=require_str(
                    policy.get("nomad_namespace"),
                    f"{path}.policies[{index}].nomad_namespace",
                ),
                instance_bounds=InstanceBounds(
                    minimum=int(bounds["min"]),
                    maximum=int(bounds["max"]),
                ),
                scale_out=ScaleOutPolicy(
                    working_set_utilization_percent=float(scale_out["working_set_utilization_percent"]),
                    sustain_minutes=int(scale_out["sustain_minutes"]),
                    oom_event_immediate=bool(scale_out["oom_event_immediate"]),
                ),
                scale_in=ScaleInPolicy(
                    working_set_utilization_percent=float(scale_in["working_set_utilization_percent"]),
                    cooldown_minutes=int(scale_in["cooldown_minutes"]),
                ),
                required_signals=tuple(policy["required_signals"]),
                allowed_mobility_tiers=tuple(policy["allowed_mobility_tiers"]),
                pause_when_lanes_active=tuple(policy["pause_when_lanes_active"]),
                notes=policy.get("notes"),
            )
        )
    return RuntimePoolAutoscalingCatalog(controller=controller, policies=tuple(policies))


def render_summary_json(catalog: RuntimePoolAutoscalingCatalog) -> str:
    payload = {
        "controller": {
            "preferred_implementation": catalog.controller.preferred_implementation,
            "metrics_source": catalog.controller.metrics_source,
            "routing_surface": catalog.controller.routing_surface,
            "invocation_surface": catalog.controller.invocation_surface,
            "receipt_directory": catalog.controller.receipt_directory,
            "pause_conditions": list(catalog.controller.pause_conditions),
        },
        "policies": [
            {
                "pool_id": policy.pool_id,
                "nomad_namespace": policy.nomad_namespace,
                "instance_bounds": {
                    "min": policy.instance_bounds.minimum,
                    "max": policy.instance_bounds.maximum,
                },
                "scale_out": {
                    "working_set_utilization_percent": policy.scale_out.working_set_utilization_percent,
                    "sustain_minutes": policy.scale_out.sustain_minutes,
                    "oom_event_immediate": policy.scale_out.oom_event_immediate,
                },
                "scale_in": {
                    "working_set_utilization_percent": policy.scale_in.working_set_utilization_percent,
                    "cooldown_minutes": policy.scale_in.cooldown_minutes,
                },
                "required_signals": list(policy.required_signals),
                "allowed_mobility_tiers": list(policy.allowed_mobility_tiers),
                "pause_when_lanes_active": list(policy.pause_when_lanes_active),
            }
            for policy in catalog.policies
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the runtime-pool autoscaling catalog and print the governed policy summary.",
    )
    parser.add_argument("--check", action="store_true", help="Validate the autoscaling catalog.")
    parser.add_argument("--json", action="store_true", help="Print the validated policy summary as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.check and not args.json:
        parser.error("one of --check or --json is required")

    try:
        catalog = load_runtime_pool_autoscaling()
        if args.json:
            print(render_summary_json(catalog), end="")
        else:
            print("Runtime pool autoscaling catalog OK: " + ", ".join(policy.pool_id for policy in catalog.policies))
        return 0
    except Exception as exc:
        return emit_cli_error("runtime-pool-autoscaling", exc)


if __name__ == "__main__":
    raise SystemExit(main())
