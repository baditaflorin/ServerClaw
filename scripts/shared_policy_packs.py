#!/usr/bin/env python3

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_bool, require_int, require_list, require_mapping, require_str

from controller_automation_toolkit import load_json, repo_path


SHARED_POLICY_PACKS_PATH: Final = repo_path("config", "shared-policy-packs.json")
SHARED_POLICY_PACKS_SCHEMA_PATH: Final = repo_path("docs", "schema", "shared-policy-packs.schema.json")


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        text = require_str(item, f"{path}[{index}]")
        if text in seen:
            raise ValueError(f"{path} must not contain duplicates")
        seen.add(text)
        normalized.append(text)
    return normalized


@dataclass(frozen=True)
class SharedPolicyPacks:
    allowed_redundancy_tiers: tuple[str, ...]
    tier_order: dict[str, int]
    standby_kind_by_tier: dict[str, str]
    live_apply_mode_by_tier: dict[str, str]
    enforced_redundancy_tiers: set[str]
    known_empty_locations: set[str]
    rehearsal_tier_sequence: tuple[str, ...]
    allowed_rehearsal_results: set[str]
    allowed_standby_modes: set[str]
    control_plane_categories: set[str]
    max_supported_tier_by_failure_domain_count: tuple[tuple[int, str], ...]
    capacity_class_ids: tuple[str, ...]
    requester_class_aliases: dict[str, str]
    primary_capacity_class_by_requester: dict[str, str]
    declared_drill_borrow_by_requester: dict[str, tuple[str, ...]]
    break_glass_borrow_by_requester: dict[str, tuple[str, ...]]
    failure_domain_kinds: set[str]
    failure_domain_statuses: set[str]
    guest_placement_classes: set[str]
    environment_placement_classes: set[str]
    reserved_capacity_exclusions: set[str]

    def max_supported_tier_for_failure_domain_count(self, failure_domain_count: int) -> str:
        if failure_domain_count < 1:
            raise ValueError("failure_domain_count must be >= 1")
        selected_tier: str | None = None
        for minimum_count, tier in self.max_supported_tier_by_failure_domain_count:
            if failure_domain_count >= minimum_count:
                selected_tier = tier
        if selected_tier is None:
            raise ValueError("shared policy packs do not define a failure-domain tier floor for this platform")
        return selected_tier


def load_shared_policy_payload(path: Path = SHARED_POLICY_PACKS_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


@cache
def load_shared_policy_packs(path: Path = SHARED_POLICY_PACKS_PATH) -> SharedPolicyPacks:
    payload = load_shared_policy_payload(path)
    path_str = str(path)

    require_str(payload.get("$schema"), f"{path_str}.$schema")
    if payload["$schema"] != "docs/schema/shared-policy-packs.schema.json":
        raise ValueError(f"{path_str}.$schema must reference docs/schema/shared-policy-packs.schema.json")
    if require_str(payload.get("schema_version"), f"{path_str}.schema_version") != "1.0.0":
        raise ValueError(f"{path_str}.schema_version must be 1.0.0")

    packs = require_mapping(payload.get("packs"), f"{path_str}.packs")

    redundancy = require_mapping(packs.get("service_redundancy"), f"{path_str}.packs.service_redundancy")
    tier_entries = require_list(redundancy.get("tiers"), f"{path_str}.packs.service_redundancy.tiers")
    if not tier_entries:
        raise ValueError(f"{path_str}.packs.service_redundancy.tiers must not be empty")

    allowed_redundancy_tiers: list[str] = []
    tier_order: dict[str, int] = {}
    standby_kind_by_tier: dict[str, str] = {}
    live_apply_mode_by_tier: dict[str, str] = {}
    enforced_redundancy_tiers: set[str] = set()
    seen_orders: set[int] = set()
    for index, entry in enumerate(tier_entries):
        entry = require_mapping(entry, f"{path_str}.packs.service_redundancy.tiers[{index}]")
        tier_id = require_str(entry.get("id"), f"{path_str}.packs.service_redundancy.tiers[{index}].id")
        if tier_id in tier_order:
            raise ValueError(f"duplicate shared policy redundancy tier '{tier_id}'")
        order = require_int(entry.get("order"), f"{path_str}.packs.service_redundancy.tiers[{index}].order", minimum=0)
        if order in seen_orders:
            raise ValueError(f"duplicate shared policy redundancy tier order {order}")
        seen_orders.add(order)
        allowed_redundancy_tiers.append(tier_id)
        tier_order[tier_id] = order
        standby_kind_by_tier[tier_id] = require_str(
            entry.get("standby_kind"),
            f"{path_str}.packs.service_redundancy.tiers[{index}].standby_kind",
        )
        live_apply_mode_by_tier[tier_id] = require_str(
            entry.get("live_apply_mode"),
            f"{path_str}.packs.service_redundancy.tiers[{index}].live_apply_mode",
        )
        if require_bool(
            entry.get("enforce_standby_capacity"),
            f"{path_str}.packs.service_redundancy.tiers[{index}].enforce_standby_capacity",
        ):
            enforced_redundancy_tiers.add(tier_id)

    if sorted(seen_orders) != list(range(len(tier_entries))):
        raise ValueError(f"{path_str}.packs.service_redundancy.tiers orders must be contiguous starting at 0")

    rehearsal_gate = require_mapping(
        redundancy.get("rehearsal_gate"),
        f"{path_str}.packs.service_redundancy.rehearsal_gate",
    )
    rehearsal_tier_sequence = tuple(
        require_string_list(
            rehearsal_gate.get("required_tiers"),
            f"{path_str}.packs.service_redundancy.rehearsal_gate.required_tiers",
        )
    )
    unknown_rehearsal_tiers = sorted(set(rehearsal_tier_sequence) - set(allowed_redundancy_tiers))
    if unknown_rehearsal_tiers:
        raise ValueError(
            f"{path_str}.packs.service_redundancy.rehearsal_gate.required_tiers references unknown tiers: "
            + ", ".join(unknown_rehearsal_tiers)
        )
    allowed_rehearsal_results = set(
        require_string_list(
            rehearsal_gate.get("allowed_results"),
            f"{path_str}.packs.service_redundancy.rehearsal_gate.allowed_results",
        )
    )
    if not allowed_rehearsal_results:
        raise ValueError(f"{path_str}.packs.service_redundancy.rehearsal_gate.allowed_results must not be empty")

    thresholds = require_list(
        redundancy.get("max_supported_tier_by_failure_domain_count"),
        f"{path_str}.packs.service_redundancy.max_supported_tier_by_failure_domain_count",
    )
    if not thresholds:
        raise ValueError(
            f"{path_str}.packs.service_redundancy.max_supported_tier_by_failure_domain_count must not be empty"
        )
    max_supported_tier_by_failure_domain_count: list[tuple[int, str]] = []
    seen_counts: set[int] = set()
    previous_count = 0
    for index, threshold in enumerate(thresholds):
        threshold = require_mapping(
            threshold,
            f"{path_str}.packs.service_redundancy.max_supported_tier_by_failure_domain_count[{index}]",
        )
        minimum_count = require_int(
            threshold.get("minimum_failure_domain_count"),
            f"{path_str}.packs.service_redundancy.max_supported_tier_by_failure_domain_count[{index}].minimum_failure_domain_count",
            minimum=1,
        )
        if minimum_count in seen_counts:
            raise ValueError(f"duplicate failure-domain threshold {minimum_count} in shared policy packs")
        if minimum_count <= previous_count:
            raise ValueError(
                f"{path_str}.packs.service_redundancy.max_supported_tier_by_failure_domain_count must be strictly ascending"
            )
        tier_id = require_str(
            threshold.get("tier"),
            f"{path_str}.packs.service_redundancy.max_supported_tier_by_failure_domain_count[{index}].tier",
        )
        if tier_id not in tier_order:
            raise ValueError(f"shared policy packs reference unknown redundancy tier '{tier_id}'")
        seen_counts.add(minimum_count)
        previous_count = minimum_count
        max_supported_tier_by_failure_domain_count.append((minimum_count, tier_id))
    if max_supported_tier_by_failure_domain_count[0][0] != 1:
        raise ValueError(
            f"{path_str}.packs.service_redundancy.max_supported_tier_by_failure_domain_count must start at 1"
        )

    known_empty_locations = set(
        require_string_list(
            redundancy.get("known_empty_locations"),
            f"{path_str}.packs.service_redundancy.known_empty_locations",
        )
    )
    allowed_standby_modes = set(
        require_string_list(
            redundancy.get("standby_modes"),
            f"{path_str}.packs.service_redundancy.standby_modes",
        )
    )
    control_plane_categories = set(
        require_string_list(
            redundancy.get("control_plane_categories"),
            f"{path_str}.packs.service_redundancy.control_plane_categories",
        )
    )

    capacity = require_mapping(packs.get("capacity_classes"), f"{path_str}.packs.capacity_classes")
    classes = require_list(capacity.get("classes"), f"{path_str}.packs.capacity_classes.classes")
    if not classes:
        raise ValueError(f"{path_str}.packs.capacity_classes.classes must not be empty")

    capacity_class_ids: list[str] = []
    requester_class_aliases: dict[str, str] = {}
    primary_capacity_class_by_requester: dict[str, str] = {}
    declared_drill_borrow_by_requester: dict[str, tuple[str, ...]] = {}
    break_glass_borrow_by_requester: dict[str, tuple[str, ...]] = {}
    pending_class_links: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = []
    for index, entry in enumerate(classes):
        entry = require_mapping(entry, f"{path_str}.packs.capacity_classes.classes[{index}]")
        class_id = require_str(entry.get("id"), f"{path_str}.packs.capacity_classes.classes[{index}].id")
        if class_id in capacity_class_ids:
            raise ValueError(f"duplicate capacity class '{class_id}' in shared policy packs")
        requester_class = require_str(
            entry.get("requester_class"),
            f"{path_str}.packs.capacity_classes.classes[{index}].requester_class",
        )
        if requester_class in primary_capacity_class_by_requester:
            raise ValueError(
                f"shared policy packs define multiple primary capacity classes for requester '{requester_class}'"
            )
        aliases = tuple(
            require_string_list(
                entry.get("aliases"),
                f"{path_str}.packs.capacity_classes.classes[{index}].aliases",
            )
        )
        if requester_class not in aliases:
            raise ValueError(
                f"{path_str}.packs.capacity_classes.classes[{index}].aliases must include requester_class '{requester_class}'"
            )
        if class_id not in aliases:
            raise ValueError(f"{path_str}.packs.capacity_classes.classes[{index}].aliases must include id '{class_id}'")
        for alias in aliases:
            existing = requester_class_aliases.get(alias)
            if existing is not None and existing != requester_class:
                raise ValueError(f"capacity class alias '{alias}' is assigned to multiple requester classes")
            requester_class_aliases[alias] = requester_class
        primary_capacity_class_by_requester[requester_class] = class_id
        capacity_class_ids.append(class_id)
        declared_drill_borrow = tuple(
            require_string_list(
                entry.get("declared_drill_borrow_from", []),
                f"{path_str}.packs.capacity_classes.classes[{index}].declared_drill_borrow_from",
            )
        )
        break_glass_borrow = tuple(
            require_string_list(
                entry.get("break_glass_borrow_from", []),
                f"{path_str}.packs.capacity_classes.classes[{index}].break_glass_borrow_from",
            )
        )
        pending_class_links.append((requester_class, class_id, declared_drill_borrow, break_glass_borrow))

    valid_capacity_classes = set(capacity_class_ids)
    for requester_class, class_id, declared_drill_borrow, break_glass_borrow in pending_class_links:
        unknown_declared = sorted(set(declared_drill_borrow) - valid_capacity_classes)
        if unknown_declared:
            raise ValueError(
                f"shared policy packs capacity class '{class_id}' references unknown declared-drill borrow classes: "
                + ", ".join(unknown_declared)
            )
        unknown_break_glass = sorted(set(break_glass_borrow) - valid_capacity_classes)
        if unknown_break_glass:
            raise ValueError(
                f"shared policy packs capacity class '{class_id}' references unknown break-glass borrow classes: "
                + ", ".join(unknown_break_glass)
            )
        declared_drill_borrow_by_requester[requester_class] = declared_drill_borrow
        break_glass_borrow_by_requester[requester_class] = break_glass_borrow

    placement = require_mapping(packs.get("placement"), f"{path_str}.packs.placement")
    failure_domain_kinds = set(
        require_string_list(
            placement.get("failure_domain_kinds"),
            f"{path_str}.packs.placement.failure_domain_kinds",
        )
    )
    failure_domain_statuses = set(
        require_string_list(
            placement.get("failure_domain_statuses"),
            f"{path_str}.packs.placement.failure_domain_statuses",
        )
    )
    guest_placement_classes = set(
        require_string_list(
            placement.get("guest_placement_classes"),
            f"{path_str}.packs.placement.guest_placement_classes",
        )
    )
    environment_placement_classes = set(
        require_string_list(
            placement.get("environment_placement_classes"),
            f"{path_str}.packs.placement.environment_placement_classes",
        )
    )
    reserved_capacity_exclusions = set(
        require_string_list(
            placement.get("reserved_capacity_exclusions"),
            f"{path_str}.packs.placement.reserved_capacity_exclusions",
        )
    )

    return SharedPolicyPacks(
        allowed_redundancy_tiers=tuple(tier_id for tier_id, _ in sorted(tier_order.items(), key=lambda item: item[1])),
        tier_order=tier_order,
        standby_kind_by_tier=standby_kind_by_tier,
        live_apply_mode_by_tier=live_apply_mode_by_tier,
        enforced_redundancy_tiers=enforced_redundancy_tiers,
        known_empty_locations=known_empty_locations,
        rehearsal_tier_sequence=rehearsal_tier_sequence,
        allowed_rehearsal_results=allowed_rehearsal_results,
        allowed_standby_modes=allowed_standby_modes,
        control_plane_categories=control_plane_categories,
        max_supported_tier_by_failure_domain_count=tuple(max_supported_tier_by_failure_domain_count),
        capacity_class_ids=tuple(capacity_class_ids),
        requester_class_aliases=requester_class_aliases,
        primary_capacity_class_by_requester=primary_capacity_class_by_requester,
        declared_drill_borrow_by_requester=declared_drill_borrow_by_requester,
        break_glass_borrow_by_requester=break_glass_borrow_by_requester,
        failure_domain_kinds=failure_domain_kinds,
        failure_domain_statuses=failure_domain_statuses,
        guest_placement_classes=guest_placement_classes,
        environment_placement_classes=environment_placement_classes,
        reserved_capacity_exclusions=reserved_capacity_exclusions,
    )
