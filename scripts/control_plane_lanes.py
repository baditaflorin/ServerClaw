#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path
from platform.repo import TOPOLOGY_HOST_VARS_PATH
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_list, require_mapping, require_str, require_string_list


CONTROL_PLANE_LANES_PATH = repo_path("config", "control-plane-lanes.json")
WORKFLOW_CATALOG_PATH = repo_path("config", "workflow-catalog.json")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ALLOWED_TRANSPORTS = {"ssh", "https", "authenticated_submission", "signed_http", "mixed"}
ALLOWED_LANE_IDS = ("command", "api", "message", "event")
ALLOWED_SURFACE_KINDS = {
    "ssh_endpoint",
    "management_api",
    "service_api",
    "mail_submission",
    "notification_profile",
    "webhook",
    "event_subject",
    "chat_channel",
}


def require_identifier(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"{path} must use lowercase letters, numbers, hyphens, or underscores")
    return value


def require_semver(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not SEMVER_PATTERN.match(value):
        raise ValueError(f"{path} must use semantic version format")
    return value


def load_workflow_ids() -> set[str]:
    catalog = require_mapping(load_json(WORKFLOW_CATALOG_PATH), str(WORKFLOW_CATALOG_PATH))
    workflows = require_mapping(catalog.get("workflows"), "workflow-catalog.workflows")
    return {require_identifier(workflow_id, f"workflow-catalog.workflows.{workflow_id}") for workflow_id in workflows}


def load_service_and_owner_refs() -> tuple[set[str], set[str]]:
    host_vars = require_mapping(load_yaml(TOPOLOGY_HOST_VARS_PATH), str(TOPOLOGY_HOST_VARS_PATH))
    topology = require_mapping(host_vars.get("lv3_service_topology"), "host_vars.lv3_service_topology")
    service_refs = {
        require_identifier(service_id, f"host_vars.lv3_service_topology.{service_id}") for service_id in topology
    }

    owners = {require_identifier(TOPOLOGY_HOST_VARS_PATH.stem, "host_vars host id")}
    guests = require_list(host_vars.get("proxmox_guests"), "host_vars.proxmox_guests")
    for index, guest in enumerate(guests):
        guest = require_mapping(guest, f"host_vars.proxmox_guests[{index}]")
        owners.add(require_identifier(guest.get("name"), f"host_vars.proxmox_guests[{index}].name"))

    return service_refs, owners


def validate_surface(
    surface: Any,
    path: str,
    workflow_ids: set[str],
    service_refs: set[str],
    owner_refs: set[str],
) -> dict[str, Any]:
    surface = require_mapping(surface, path)
    surface_id = require_identifier(surface.get("id"), f"{path}.id")
    kind = require_str(surface.get("kind"), f"{path}.kind")
    if kind not in ALLOWED_SURFACE_KINDS:
        raise ValueError(f"{path}.kind must be one of {sorted(ALLOWED_SURFACE_KINDS)}")

    require_str(surface.get("endpoint"), f"{path}.endpoint")
    require_str(surface.get("auth"), f"{path}.auth")
    require_str(surface.get("notes"), f"{path}.notes")

    service_ref_values = require_string_list(surface.get("service_refs", []), f"{path}.service_refs")
    for index, ref in enumerate(service_ref_values):
        require_identifier(ref, f"{path}.service_refs[{index}]")
        if ref not in service_refs:
            raise ValueError(f"{path}.service_refs[{index}] references unknown service '{ref}'")

    owner_ref_values = require_string_list(surface.get("owner_refs", []), f"{path}.owner_refs")
    for index, ref in enumerate(owner_ref_values):
        require_identifier(ref, f"{path}.owner_refs[{index}]")
        if ref not in owner_refs:
            raise ValueError(f"{path}.owner_refs[{index}] references unknown owner '{ref}'")

    workflow_ref_values = require_string_list(surface.get("workflow_refs", []), f"{path}.workflow_refs")
    for index, ref in enumerate(workflow_ref_values):
        require_identifier(ref, f"{path}.workflow_refs[{index}]")
        if ref not in workflow_ids:
            raise ValueError(f"{path}.workflow_refs[{index}] references unknown workflow '{ref}'")

    if not service_ref_values and not owner_ref_values:
        raise ValueError(f"{path} must define at least one service_refs or owner_refs entry")

    return {
        "id": surface_id,
        "kind": kind,
        "endpoint": surface["endpoint"],
        "workflow_refs": workflow_ref_values,
    }


def validate_lane_catalog(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    require_semver(catalog.get("schema_version"), "control-plane-lanes.schema_version")
    lanes = require_mapping(catalog.get("lanes"), "control-plane-lanes.lanes")
    if set(lanes.keys()) != set(ALLOWED_LANE_IDS):
        raise ValueError(f"control-plane-lanes.lanes must define exactly {list(ALLOWED_LANE_IDS)}")

    workflow_ids = load_workflow_ids()
    service_refs, owner_refs = load_service_and_owner_refs()
    normalized_lanes: dict[str, dict[str, Any]] = {}

    for lane_id in ALLOWED_LANE_IDS:
        lane = require_mapping(lanes.get(lane_id), f"control-plane-lanes.lanes.{lane_id}")
        require_str(lane.get("title"), f"control-plane-lanes.lanes.{lane_id}.title")
        require_str(lane.get("purpose"), f"control-plane-lanes.lanes.{lane_id}.purpose")
        transport = require_str(lane.get("transport"), f"control-plane-lanes.lanes.{lane_id}.transport")
        if transport not in ALLOWED_TRANSPORTS:
            raise ValueError(
                f"control-plane-lanes.lanes.{lane_id}.transport must be one of {sorted(ALLOWED_TRANSPORTS)}"
            )
        network_paths = require_string_list(
            lane.get("network_paths"), f"control-plane-lanes.lanes.{lane_id}.network_paths"
        )
        steady_state_rules = require_string_list(
            lane.get("steady_state_rules"), f"control-plane-lanes.lanes.{lane_id}.steady_state_rules"
        )
        if not network_paths:
            raise ValueError(f"control-plane-lanes.lanes.{lane_id}.network_paths must not be empty")
        if not steady_state_rules:
            raise ValueError(f"control-plane-lanes.lanes.{lane_id}.steady_state_rules must not be empty")
        require_str(
            lane.get("identity_boundary"),
            f"control-plane-lanes.lanes.{lane_id}.identity_boundary",
        )

        current_surfaces = require_list(
            lane.get("current_surfaces"), f"control-plane-lanes.lanes.{lane_id}.current_surfaces"
        )
        if not current_surfaces:
            raise ValueError(f"control-plane-lanes.lanes.{lane_id}.current_surfaces must not be empty")

        seen_surface_ids: set[str] = set()
        normalized_surfaces = []
        for index, surface in enumerate(current_surfaces):
            normalized = validate_surface(
                surface,
                f"control-plane-lanes.lanes.{lane_id}.current_surfaces[{index}]",
                workflow_ids,
                service_refs,
                owner_refs,
            )
            if normalized["id"] in seen_surface_ids:
                raise ValueError(f"duplicate surface id '{normalized['id']}' in lane '{lane_id}'")
            seen_surface_ids.add(normalized["id"])
            normalized_surfaces.append(normalized)

        normalized_lanes[lane_id] = {
            "title": lane["title"],
            "transport": transport,
            "steady_state_rules": steady_state_rules,
            "current_surfaces": normalized_surfaces,
        }

    return normalized_lanes


def load_lane_catalog() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    catalog = require_mapping(load_json(CONTROL_PLANE_LANES_PATH), str(CONTROL_PLANE_LANES_PATH))
    normalized_lanes = validate_lane_catalog(catalog)
    return catalog, normalized_lanes


def list_lanes(normalized_lanes: dict[str, dict[str, Any]]) -> int:
    print(f"Control-plane lane catalog: {CONTROL_PLANE_LANES_PATH}")
    print("Available lanes:")
    for lane_id in ALLOWED_LANE_IDS:
        lane = normalized_lanes[lane_id]
        print(f"  - {lane_id}: {lane['title']} [{lane['transport']}, {len(lane['current_surfaces'])} surfaces]")
    return 0


def show_lane(catalog: dict[str, Any], normalized_lanes: dict[str, dict[str, Any]], lane_id: str) -> int:
    if lane_id not in normalized_lanes:
        print(f"Unknown control-plane lane: {lane_id}", file=sys.stderr)
        return 2

    lane = catalog["lanes"][lane_id]
    normalized_lane = normalized_lanes[lane_id]
    print(f"Lane: {lane_id}")
    print(f"Title: {lane['title']}")
    print(f"Purpose: {lane['purpose']}")
    print(f"Transport: {lane['transport']}")
    print("Network paths:")
    for path in lane["network_paths"]:
        print(f"  - {path}")
    print(f"Identity boundary: {lane['identity_boundary']}")
    print("Steady-state rules:")
    for rule in lane["steady_state_rules"]:
        print(f"  - {rule}")
    print("Current surfaces:")
    for surface in normalized_lane["current_surfaces"]:
        print(f"  - {surface['id']} [{surface['kind']}]: {surface['endpoint']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or validate the canonical control-plane communication-lane catalog."
    )
    parser.add_argument("--list", action="store_true", help="List the available lanes.")
    parser.add_argument("--lane", help="Show one lane from the catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the lane catalog.")
    args = parser.parse_args()

    try:
        catalog, normalized_lanes = load_lane_catalog()
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        return emit_cli_error("Control-plane lanes", exc)

    if args.validate:
        print(f"Control-plane lane catalog OK: {CONTROL_PLANE_LANES_PATH}")
        return 0

    if args.lane:
        return show_lane(catalog, normalized_lanes, args.lane)

    return list_lanes(normalized_lanes)


if __name__ == "__main__":
    sys.exit(main())
