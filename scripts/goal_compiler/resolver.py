"""
Target resolver for the deterministic goal compiler (ADR 0112).

Given a matched rule and its template captures, the resolver:
  1. Looks up the target service in the service-capability catalog
  2. Expands alias groups (e.g. "monitoring stack" → grafana + loki + prometheus)
  3. Derives the allowed VM hosts from catalog data
  4. Falls back gracefully when catalog data is absent

This module has no hard dependency on the platform/ package tree and only
imports from scripts/ and the standard library, so it can be loaded by the
goal compiler without triggering the platform module-loader dance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import IntentScope, IntentTarget


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else (default or {})
    except (OSError, json.JSONDecodeError):
        return default or {}


def _normalize(value: str) -> str:
    return value.strip().lower().replace("-", "_")


# ---------------------------------------------------------------------------
# Service catalog wrapper
# ---------------------------------------------------------------------------


def _service_map(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Return a {service_id: service_dict} mapping from the capability catalog."""
    payload = _load_json(repo_root / "config" / "service-capability-catalog.json")
    services = payload.get("services", [])
    if not isinstance(services, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in services:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            result[item["id"]] = item
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_target(
    target_kind: str,
    captures: dict[str, str],
    alias_groups: dict[str, Any],
    service_aliases: dict[str, str],
    repo_root: Path,
) -> IntentTarget:
    """
    Derive an IntentTarget from rule captures and the service catalog.

    Parameters
    ----------
    target_kind:
        The ``target_kind`` field from the matched GoalRule
        (``"service"``, ``"workflow"``, ``"vmid"``, ``"platform"``, etc.)
    captures:
        Template captures from the matched rule pattern (e.g. ``{"service": "netbox"}``).
    alias_groups:
        The ``groups`` mapping from ``goal-compiler-aliases.yaml``.
    service_aliases:
        The ``service_aliases`` mapping from ``goal-compiler-aliases.yaml``.
    repo_root:
        Absolute path to the repository root for catalog lookups.
    """
    services = _service_map(repo_root)

    if target_kind == "workflow":
        workflow_name = captures.get("workflow", "")
        return IntentTarget(kind="workflow", name=workflow_name)

    # --- service / service_group ---
    service_name = captures.get("service") or captures.get("target")
    if service_name:
        # Check alias groups first
        group_data = alias_groups.get(service_name)
        if group_data is not None:
            group_services = list(group_data.get("services", []))
            group_hosts = list(group_data.get("hosts", []))
            # Supplement hosts from catalog if not already listed
            for svc_id in group_services:
                catalog_entry = services.get(svc_id, {})
                vm = catalog_entry.get("vm")
                if isinstance(vm, str) and vm and vm not in group_hosts:
                    group_hosts.append(vm)
            return IntentTarget(
                kind="service_group",
                name=service_name,
                services=group_services,
                hosts=group_hosts,
            )

        # Resolve service aliases
        service_id = service_aliases.get(service_name, service_name)
        catalog_entry = services.get(service_id, {})
        vm = catalog_entry.get("vm")
        hosts = [vm] if isinstance(vm, str) and vm else []
        return IntentTarget(
            kind="service",
            name=service_id,
            services=[service_id],
            hosts=hosts,
        )

    # --- vmid ---
    vmid_raw = captures.get("vmid")
    if vmid_raw and vmid_raw.isdigit():
        return IntentTarget(kind="vmid", name=vmid_raw, vmids=[int(vmid_raw)])

    # --- platform / repository fallback ---
    name = captures.get("name", target_kind)
    return IntentTarget(kind=target_kind, name=name)


def resolve_scope(
    rule_scope_defaults: dict[str, list[Any]],
    target: IntentTarget,
) -> IntentScope:
    """
    Merge rule-level scope defaults with target-derived host/service/vmid lists.

    The rule's ``scope_defaults`` lists are the canonical *allowed* sets declared
    in the rule table.  The target resolution (``resolve_target``) adds the hosts
    and VMIDs that are known from the service catalog at compile time.
    """
    allowed_hosts = list(dict.fromkeys(rule_scope_defaults.get("allowed_hosts", []) + target.hosts))
    allowed_services = list(dict.fromkeys(rule_scope_defaults.get("allowed_services", []) + target.services))
    allowed_vmids = list(dict.fromkeys(rule_scope_defaults.get("allowed_vmids", []) + target.vmids))
    return IntentScope(
        allowed_hosts=allowed_hosts,
        allowed_services=allowed_services,
        allowed_vmids=allowed_vmids,
    )


def resolve_workflow_id(
    rule_workflow_id: str | None,
    rule_workflow_candidates: list[str],
    captures: dict[str, str],
    target: IntentTarget,
    alias_groups: dict[str, Any],
) -> str | None:
    """
    Choose the best workflow ID for the compiled intent.

    Priority:
    1. Group alias ``workflow_id`` (if the target is a group alias)
    2. Rule ``workflow_id`` (rendered with captures)
    3. First non-empty candidate from ``workflow_candidates`` (rendered with captures)
    """
    group_data = alias_groups.get(target.name)
    if group_data is not None:
        group_workflow = group_data.get("workflow_id")
        if isinstance(group_workflow, str) and group_workflow.strip():
            return group_workflow

    def render(template: str | None) -> str | None:
        if not template:
            return None
        mapping = {
            **captures,
            "service": target.services[0] if target.services else target.name,
            "target": target.name,
        }
        try:
            return template.format_map(mapping) or None
        except (KeyError, ValueError):
            return template or None

    if rule_workflow_id:
        rendered = render(rule_workflow_id)
        if rendered:
            return rendered

    for candidate in rule_workflow_candidates:
        rendered = render(candidate)
        if rendered:
            return rendered

    return None
