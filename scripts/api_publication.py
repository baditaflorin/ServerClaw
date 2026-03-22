#!/usr/bin/env python3

import argparse
import json
import sys
from typing import Any

from control_plane_lanes import ALLOWED_LANE_IDS, load_lane_catalog, require_identifier
from controller_automation_toolkit import emit_cli_error, load_json, repo_path


API_PUBLICATION_PATH = repo_path("config", "api-publication.json")
ALLOWED_PUBLICATION_TIERS = ("internal-only", "operator-only", "public-edge")
ALLOWED_HTTP_LANES = {"api", "event"}


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(require_str(item, f"{path}[{index}]"))
    return result


def build_lane_surface_index(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    surface_index: dict[str, dict[str, Any]] = {}
    for lane_id in ALLOWED_LANE_IDS:
        lane = require_mapping(catalog["lanes"].get(lane_id), f"control-plane-lanes.lanes.{lane_id}")
        for index, surface in enumerate(
            require_list(lane.get("current_surfaces"), f"control-plane-lanes.lanes.{lane_id}.current_surfaces")
        ):
            surface = require_mapping(
                surface,
                f"control-plane-lanes.lanes.{lane_id}.current_surfaces[{index}]",
            )
            surface_id = require_identifier(surface.get("id"), f"control-plane-lanes surface {lane_id}[{index}]")
            if surface_id in surface_index:
                raise ValueError(f"duplicate control-plane surface id '{surface_id}'")
            surface_index[surface_id] = {
                "lane": lane_id,
                "kind": require_str(surface.get("kind"), f"control-plane surface {surface_id}.kind"),
                "endpoint": require_str(surface.get("endpoint"), f"control-plane surface {surface_id}.endpoint"),
            }
    return surface_index


def validate_api_publication_catalog(
    catalog: dict[str, Any],
    lane_catalog: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    schema_version = require_str(catalog.get("schema_version"), "api-publication.schema_version")
    if schema_version != "1.0.0":
        raise ValueError("api-publication.schema_version must be '1.0.0'")

    default_tier = require_str(
        catalog.get("default_publication_tier"),
        "api-publication.default_publication_tier",
    )
    if default_tier != "internal-only":
        raise ValueError("api-publication.default_publication_tier must stay 'internal-only'")

    tiers = require_mapping(catalog.get("tiers"), "api-publication.tiers")
    if set(tiers.keys()) != set(ALLOWED_PUBLICATION_TIERS):
        raise ValueError(
            f"api-publication.tiers must define exactly {list(ALLOWED_PUBLICATION_TIERS)}"
        )

    normalized_tiers: dict[str, dict[str, Any]] = {}
    for tier_id in ALLOWED_PUBLICATION_TIERS:
        tier = require_mapping(tiers.get(tier_id), f"api-publication.tiers.{tier_id}")
        normalized_tiers[tier_id] = {
          "title": require_str(tier.get("title"), f"api-publication.tiers.{tier_id}.title"),
          "summary": require_str(tier.get("summary"), f"api-publication.tiers.{tier_id}.summary"),
          "approval_rule": require_str(
              tier.get("approval_rule"),
              f"api-publication.tiers.{tier_id}.approval_rule",
          ),
        }

    lane_surface_index = build_lane_surface_index(lane_catalog)
    governed_http_surface_ids = {
        surface_id
        for surface_id, surface in lane_surface_index.items()
        if surface["lane"] in ALLOWED_HTTP_LANES
    }

    surfaces = require_list(catalog.get("surfaces"), "api-publication.surfaces")
    if not surfaces:
        raise ValueError("api-publication.surfaces must not be empty")

    normalized_surfaces: list[dict[str, Any]] = []
    seen_surface_ids: set[str] = set()
    seen_lane_surface_refs: set[str] = set()
    for index, surface in enumerate(surfaces):
        path = f"api-publication.surfaces[{index}]"
        surface = require_mapping(surface, path)
        surface_id = require_identifier(surface.get("id"), f"{path}.id")
        if surface_id in seen_surface_ids:
            raise ValueError(f"duplicate api-publication surface id '{surface_id}'")
        seen_surface_ids.add(surface_id)

        title = require_str(surface.get("title"), f"{path}.title")
        lane = require_str(surface.get("lane"), f"{path}.lane")
        if lane not in ALLOWED_HTTP_LANES:
            raise ValueError(f"{path}.lane must be one of {sorted(ALLOWED_HTTP_LANES)}")

        publication_tier = require_str(surface.get("publication_tier"), f"{path}.publication_tier")
        if publication_tier not in ALLOWED_PUBLICATION_TIERS:
            raise ValueError(
                f"{path}.publication_tier must be one of {list(ALLOWED_PUBLICATION_TIERS)}"
            )

        lane_surface_ref = require_identifier(surface.get("lane_surface_ref"), f"{path}.lane_surface_ref")
        lane_surface = lane_surface_index.get(lane_surface_ref)
        if lane_surface is None:
            raise ValueError(f"{path}.lane_surface_ref references unknown lane surface '{lane_surface_ref}'")
        if lane_surface["lane"] != lane:
            raise ValueError(
                f"{path}.lane must match lane surface '{lane_surface_ref}' ({lane_surface['lane']})"
            )
        if lane_surface_ref in seen_lane_surface_refs:
            raise ValueError(f"lane surface '{lane_surface_ref}' is classified more than once")
        seen_lane_surface_refs.add(lane_surface_ref)

        public_hostnames = require_string_list(surface.get("public_hostnames", []), f"{path}.public_hostnames")
        if publication_tier == "public-edge" and not public_hostnames:
            raise ValueError(f"{path}.public_hostnames must not be empty for public-edge surfaces")
        if publication_tier != "public-edge" and public_hostnames:
            raise ValueError(f"{path}.public_hostnames must stay empty unless publication_tier is public-edge")

        normalized_surfaces.append(
            {
                "id": surface_id,
                "title": title,
                "lane": lane,
                "lane_surface_ref": lane_surface_ref,
                "kind": lane_surface["kind"],
                "endpoint": lane_surface["endpoint"],
                "publication_tier": publication_tier,
                "reachability": require_str(surface.get("reachability"), f"{path}.reachability"),
                "approval_notes": require_str(surface.get("approval_notes"), f"{path}.approval_notes"),
                "public_hostnames": public_hostnames,
            }
        )

    missing_classifications = sorted(governed_http_surface_ids - seen_lane_surface_refs)
    if missing_classifications:
        raise ValueError(
            "api-publication.surfaces must classify every API/event lane surface: "
            + ", ".join(missing_classifications)
        )

    return normalized_tiers, normalized_surfaces


def load_api_publication_catalog() -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    catalog = require_mapping(load_json(API_PUBLICATION_PATH), str(API_PUBLICATION_PATH))
    lane_catalog, _normalized_lanes = load_lane_catalog()
    normalized_tiers, normalized_surfaces = validate_api_publication_catalog(catalog, lane_catalog)
    return catalog, normalized_tiers, normalized_surfaces


def list_publication_catalog(
    normalized_tiers: dict[str, dict[str, Any]],
    normalized_surfaces: list[dict[str, Any]],
) -> int:
    print(f"API publication catalog: {API_PUBLICATION_PATH}")
    print("Publication tiers:")
    for tier_id in ALLOWED_PUBLICATION_TIERS:
        tier = normalized_tiers[tier_id]
        surface_count = sum(1 for surface in normalized_surfaces if surface["publication_tier"] == tier_id)
        print(f"  - {tier_id}: {tier['title']} [{surface_count} surfaces]")
    print("Classified surfaces:")
    for surface in normalized_surfaces:
        print(
            f"  - {surface['id']} [{surface['publication_tier']}, {surface['lane']}, {surface['kind']}]: "
            f"{surface['endpoint']}"
        )
    return 0


def show_surface(
    normalized_tiers: dict[str, dict[str, Any]],
    normalized_surfaces: list[dict[str, Any]],
    surface_id: str,
) -> int:
    surface = next((item for item in normalized_surfaces if item["id"] == surface_id), None)
    if surface is None:
        print(f"Unknown API publication surface: {surface_id}", file=sys.stderr)
        return 2

    tier = normalized_tiers[surface["publication_tier"]]
    print(f"Surface: {surface['id']}")
    print(f"Title: {surface['title']}")
    print(f"Lane: {surface['lane']}")
    print(f"Kind: {surface['kind']}")
    print(f"Endpoint: {surface['endpoint']}")
    print(f"Publication tier: {surface['publication_tier']}")
    print(f"Tier summary: {tier['summary']}")
    print(f"Reachability: {surface['reachability']}")
    print(f"Approval notes: {surface['approval_notes']}")
    if surface["public_hostnames"]:
        print("Public hostnames:")
        for hostname in surface["public_hostnames"]:
            print(f"  - {hostname}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or validate the canonical private-first API publication catalog."
    )
    parser.add_argument("--list", action="store_true", help="List publication tiers and classified surfaces.")
    parser.add_argument("--surface", help="Show one classified API or webhook surface.")
    parser.add_argument("--validate", action="store_true", help="Validate the API publication catalog.")
    args = parser.parse_args()

    try:
        _catalog, normalized_tiers, normalized_surfaces = load_api_publication_catalog()
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        return emit_cli_error("API publication", exc)

    if args.validate:
        print(f"API publication catalog OK: {API_PUBLICATION_PATH}")
        return 0
    if args.surface:
        return show_surface(normalized_tiers, normalized_surfaces, args.surface)
    return list_publication_catalog(normalized_tiers, normalized_surfaces)


if __name__ == "__main__":
    sys.exit(main())
