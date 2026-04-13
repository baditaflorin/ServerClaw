#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
existing_platform = sys.modules.get("platform")
if existing_platform is not None and not hasattr(existing_platform, "__path__"):
    del sys.modules["platform"]

from platform.repo import TOPOLOGY_HOST, TOPOLOGY_HOST_VARS_PATH

from validation_toolkit import require_int, require_list, require_mapping, require_str

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from service_id_resolver import resolve_service_id
from shared_policy_packs import load_shared_policy_packs

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
    ) from exc


SERVICE_REDUNDANCY_PATH: Final = repo_path("config", "service-redundancy-catalog.json")
SERVICE_REDUNDANCY_SCHEMA_PATH: Final = repo_path("docs", "schema", "service-redundancy-catalog.schema.json")
SERVICE_CATALOG_PATH: Final = repo_path("config", "service-capability-catalog.json")

SHARED_POLICIES = load_shared_policy_packs()
TIER_ORDER = SHARED_POLICIES.tier_order
STANDBY_KIND_BY_TIER = SHARED_POLICIES.standby_kind_by_tier
LIVE_APPLY_MODE_BY_TIER = SHARED_POLICIES.live_apply_mode_by_tier
KNOWN_EMPTY_LOCATIONS = SHARED_POLICIES.known_empty_locations
REHEARSAL_TIER_SEQUENCE = SHARED_POLICIES.rehearsal_tier_sequence
ALLOWED_REHEARSAL_RESULTS = SHARED_POLICIES.allowed_rehearsal_results


def require_enum(value: Any, path: str, allowed: set[str]) -> str:
    value = require_str(value, path)
    if value not in allowed:
        raise ValueError(f"{path} must be one of {sorted(allowed)}")
    return value


def require_date(value: Any, path: str) -> date:
    value = require_str(value, path)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{path} must use YYYY-MM-DD") from exc


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        normalized_item = require_str(item, f"{path}[{index}]")
        if normalized_item in seen:
            raise ValueError(f"{path} must not contain duplicates")
        seen.add(normalized_item)
        normalized.append(normalized_item)
    return normalized


def load_redundancy_catalog() -> dict[str, Any]:
    payload = load_json(SERVICE_REDUNDANCY_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{SERVICE_REDUNDANCY_PATH} must be an object")
    return normalize_redundancy_catalog(payload)


def normalize_redundancy_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    allowed_root = {"$schema", "schema_version", "platform", "services"}
    extras = {key: value for key, value in payload.items() if key not in allowed_root}
    if not extras:
        return payload

    services = payload.get("services")
    if not isinstance(services, dict):
        services = {}

    collided = []
    for key, value in extras.items():
        if key in services:
            collided.append(key)
            continue
        services[key] = value

    if collided:
        print(
            "WARN service redundancy catalog: duplicate legacy service entries ignored: " + ", ".join(sorted(collided)),
            file=sys.stderr,
        )

    for key in extras:
        payload.pop(key, None)
    payload["services"] = services

    legacy_service_keys = {
        "tier",
        "recovery_objective",
        "backup_sources",
        "standby",
        "notes",
        "rehearsal",
    }
    leaked_keys = legacy_service_keys.intersection(services)
    if leaked_keys:
        for key in leaked_keys:
            services.pop(key, None)
        print(
            "WARN service redundancy catalog: removed legacy inline keys from services: "
            + ", ".join(sorted(leaked_keys)),
            file=sys.stderr,
        )

    print(
        "WARN service redundancy catalog: normalized legacy top-level service entries into 'services'",
        file=sys.stderr,
    )
    return payload


def load_service_catalog_index() -> dict[str, dict[str, Any]]:
    payload = load_json(SERVICE_CATALOG_PATH)
    services = require_list(payload.get("services"), "config/service-capability-catalog.json.services")
    index: dict[str, dict[str, Any]] = {}
    for index_number, service in enumerate(services):
        service = require_mapping(service, f"config/service-capability-catalog.json.services[{index_number}]")
        service_id = require_str(
            service.get("id"), f"config/service-capability-catalog.json.services[{index_number}].id"
        )
        index[service_id] = service
    return index


def active_service_ids(service_catalog_index: dict[str, dict[str, Any]]) -> list[str]:
    active_ids = []
    for service_id, service in sorted(service_catalog_index.items()):
        if service.get("lifecycle_status") == "active":
            active_ids.append(service_id)
    return active_ids


def known_locations() -> set[str]:
    host_vars = load_yaml(TOPOLOGY_HOST_VARS_PATH)
    guests = require_list(host_vars.get("proxmox_guests"), "inventory/host_vars/proxmox-host.yml.proxmox_guests")
    locations = {TOPOLOGY_HOST}
    for index, guest in enumerate(guests):
        guest = require_mapping(guest, f"inventory/host_vars/proxmox-host.yml.proxmox_guests[{index}]")
        locations.add(
            require_str(guest.get("name"), f"inventory/host_vars/proxmox-host.yml.proxmox_guests[{index}].name")
        )
    return locations


def max_supported_tier_for_domains(failure_domain_count: int) -> str:
    return SHARED_POLICIES.max_supported_tier_for_failure_domain_count(failure_domain_count)


def required_rehearsal_tiers(declared_tier: str) -> list[str]:
    return [tier for tier in REHEARSAL_TIER_SEQUENCE if TIER_ORDER[tier] <= TIER_ORDER[declared_tier]]


def load_rehearsal_gate_policies(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    platform = require_mapping(catalog.get("platform"), "platform")
    rehearsal_gate = require_mapping(platform.get("rehearsal_gate"), "platform.rehearsal_gate")
    tiers = require_mapping(rehearsal_gate.get("tiers"), "platform.rehearsal_gate.tiers")
    if set(tiers) != set(REHEARSAL_TIER_SEQUENCE):
        raise ValueError("platform.rehearsal_gate.tiers must define exactly " + ", ".join(REHEARSAL_TIER_SEQUENCE))

    normalized: dict[str, dict[str, Any]] = {}
    for tier in REHEARSAL_TIER_SEQUENCE:
        policy = require_mapping(tiers.get(tier), f"platform.rehearsal_gate.tiers.{tier}")
        normalized[tier] = {
            "tier": tier,
            "exercise": require_str(
                policy.get("exercise"),
                f"platform.rehearsal_gate.tiers.{tier}.exercise",
            ),
            "freshness_window_days": require_int(
                policy.get("freshness_window_days"),
                f"platform.rehearsal_gate.tiers.{tier}.freshness_window_days",
                minimum=1,
            ),
        }
    return normalized


def normalized_rehearsal_metadata(
    catalog: dict[str, Any],
    service_id: str,
    entry: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    policies = {tier: dict(policy) for tier, policy in load_rehearsal_gate_policies(catalog).items()}

    rehearsal = entry.get("rehearsal")
    if rehearsal is None:
        return policies, []

    rehearsal = require_mapping(rehearsal, f"services.{service_id}.rehearsal")
    overrides = rehearsal.get("policies", {})
    if overrides is None:
        overrides = {}
    overrides = require_mapping(overrides, f"services.{service_id}.rehearsal.policies")
    for tier, override in overrides.items():
        if tier not in REHEARSAL_TIER_SEQUENCE:
            raise ValueError(
                f"services.{service_id}.rehearsal.policies.{tier} must target one of {list(REHEARSAL_TIER_SEQUENCE)}"
            )
        override = require_mapping(override, f"services.{service_id}.rehearsal.policies.{tier}")
        policies[tier] = {
            "tier": tier,
            "exercise": require_str(
                override.get("exercise"),
                f"services.{service_id}.rehearsal.policies.{tier}.exercise",
            ),
            "freshness_window_days": require_int(
                override.get("freshness_window_days"),
                f"services.{service_id}.rehearsal.policies.{tier}.freshness_window_days",
                minimum=1,
            ),
        }

    proofs_raw = rehearsal.get("proofs", [])
    if proofs_raw is None:
        proofs_raw = []
    proofs_raw = require_list(proofs_raw, f"services.{service_id}.rehearsal.proofs")
    proofs: list[dict[str, Any]] = []
    for index, proof in enumerate(proofs_raw):
        proof = require_mapping(proof, f"services.{service_id}.rehearsal.proofs[{index}]")
        proves_tier = require_enum(
            proof.get("proves_tier"),
            f"services.{service_id}.rehearsal.proofs[{index}].proves_tier",
            set(REHEARSAL_TIER_SEQUENCE),
        )
        performed_on = require_date(
            proof.get("performed_on"),
            f"services.{service_id}.rehearsal.proofs[{index}].performed_on",
        )
        result = require_enum(
            proof.get("result"),
            f"services.{service_id}.rehearsal.proofs[{index}].result",
            ALLOWED_REHEARSAL_RESULTS,
        )
        require_str(
            proof.get("exercise"),
            f"services.{service_id}.rehearsal.proofs[{index}].exercise",
        )
        require_str(
            proof.get("trigger"),
            f"services.{service_id}.rehearsal.proofs[{index}].trigger",
        )
        require_str(
            proof.get("target_environment"),
            f"services.{service_id}.rehearsal.proofs[{index}].target_environment",
        )
        require_int(
            proof.get("duration_minutes"),
            f"services.{service_id}.rehearsal.proofs[{index}].duration_minutes",
            minimum=0,
        )
        require_int(
            proof.get("observed_rto_seconds"),
            f"services.{service_id}.rehearsal.proofs[{index}].observed_rto_seconds",
            minimum=0,
        )
        require_str(
            proof.get("observed_data_loss"),
            f"services.{service_id}.rehearsal.proofs[{index}].observed_data_loss",
        )
        require_str(
            proof.get("health_verification"),
            f"services.{service_id}.rehearsal.proofs[{index}].health_verification",
        )
        require_str(
            proof.get("rollback_result"),
            f"services.{service_id}.rehearsal.proofs[{index}].rollback_result",
        )
        require_str(
            proof.get("evidence_ref"),
            f"services.{service_id}.rehearsal.proofs[{index}].evidence_ref",
        )
        proofs.append(
            {
                "proves_tier": proves_tier,
                "performed_on": performed_on,
                "result": result,
                "exercise": proof["exercise"],
                "trigger": proof["trigger"],
                "target_environment": proof["target_environment"],
                "duration_minutes": proof["duration_minutes"],
                "observed_rto_seconds": proof["observed_rto_seconds"],
                "observed_data_loss": proof["observed_data_loss"],
                "health_verification": proof["health_verification"],
                "rollback_result": proof["rollback_result"],
                "evidence_ref": proof["evidence_ref"],
            }
        )

    proofs.sort(
        key=lambda item: (item["performed_on"].isoformat(), item["proves_tier"], item["result"]),
        reverse=True,
    )
    return policies, proofs


def evaluate_rehearsal_gate(
    catalog: dict[str, Any],
    service_id: str,
    *,
    reference_date: date | None = None,
) -> dict[str, Any]:
    services = require_mapping(catalog.get("services"), "services")
    if service_id not in services:
        raise ValueError(f"unknown service: {service_id}")

    entry = require_mapping(services[service_id], f"services.{service_id}")
    declared_tier = require_enum(entry.get("tier"), f"services.{service_id}.tier", set(TIER_ORDER))
    reference_date = reference_date or date.today()
    policies, proofs = normalized_rehearsal_metadata(catalog, service_id, entry)

    required_policies = [dict(policies[tier]) for tier in required_rehearsal_tiers(declared_tier)]
    latest_pass_by_tier: dict[str, dict[str, Any]] = {}
    latest_proof_by_tier: dict[str, dict[str, Any]] = {}
    for proof in proofs:
        proof_tier = proof["proves_tier"]
        latest_proof_by_tier.setdefault(proof_tier, proof)
        if proof["result"] == "pass":
            latest_pass_by_tier.setdefault(proof_tier, proof)

    if declared_tier == "R0":
        return {
            "declared_tier": declared_tier,
            "implemented_tier": "R0",
            "status": "not_required",
            "summary": "No rehearsal is required for R0 services.",
            "required_policies": [],
            "proofs": proofs,
            "qualifying_proof": None,
        }

    for candidate_tier in reversed(required_rehearsal_tiers(declared_tier)):
        candidate_policy = policies[candidate_tier]
        candidate_pass = latest_pass_by_tier.get(candidate_tier)
        if candidate_pass is None:
            continue
        expires_on = candidate_pass["performed_on"] + timedelta(days=candidate_policy["freshness_window_days"])
        if reference_date <= expires_on:
            status = "fresh" if candidate_tier == declared_tier else "downgraded"
            return {
                "declared_tier": declared_tier,
                "implemented_tier": candidate_tier,
                "status": status,
                "summary": (
                    f"Fresh {candidate_tier} rehearsal from {candidate_pass['performed_on'].isoformat()} "
                    f"via {candidate_policy['exercise']} is valid until {expires_on.isoformat()}."
                ),
                "required_policies": required_policies,
                "proofs": proofs,
                "qualifying_proof": {**candidate_pass, "expires_on": expires_on},
            }

    latest_declared_proof = latest_proof_by_tier.get(declared_tier)
    if latest_declared_proof is None:
        summary = f"No recorded {declared_tier} rehearsal proof keeps the implemented claim above R0."
        status = "unproven"
    elif latest_declared_proof["result"] != "pass":
        summary = (
            f"The latest {declared_tier} rehearsal on {latest_declared_proof['performed_on'].isoformat()} "
            f"did not pass, so the implemented claim falls back to R0."
        )
        status = "downgraded"
    else:
        declared_policy = policies[declared_tier]
        expires_on = latest_declared_proof["performed_on"] + timedelta(days=declared_policy["freshness_window_days"])
        summary = (
            f"The latest passing {declared_tier} rehearsal from {latest_declared_proof['performed_on'].isoformat()} "
            f"expired on {expires_on.isoformat()}, so the implemented claim falls back to R0."
        )
        status = "downgraded"

    return {
        "declared_tier": declared_tier,
        "implemented_tier": "R0",
        "status": status,
        "summary": summary,
        "required_policies": required_policies,
        "proofs": proofs,
        "qualifying_proof": None,
    }


def effective_tier(
    declared_tier: str,
    platform_max_tier: str,
    *,
    allow_fallback: bool = False,
) -> str:
    if TIER_ORDER[declared_tier] <= TIER_ORDER[platform_max_tier]:
        return declared_tier
    if not allow_fallback:
        raise ValueError(
            f"declared tier {declared_tier} exceeds the current platform limit {platform_max_tier}; "
            "downgrade the declaration or add another failure domain first"
        )
    return platform_max_tier


def validate_redundancy_catalog(catalog: dict[str, Any]) -> None:
    jsonschema.validate(
        instance=catalog,
        schema=load_json(SERVICE_REDUNDANCY_SCHEMA_PATH),
    )

    platform = require_mapping(catalog.get("platform"), "platform")
    failure_domain_count = require_int(platform.get("failure_domain_count"), "platform.failure_domain_count", minimum=1)
    max_supported_tier = require_enum(
        platform.get("max_supported_tier"),
        "platform.max_supported_tier",
        set(TIER_ORDER),
    )
    expected_max_tier = max_supported_tier_for_domains(failure_domain_count)
    if TIER_ORDER[max_supported_tier] > TIER_ORDER[expected_max_tier]:
        raise ValueError("platform.max_supported_tier exceeds what the declared failure_domain_count supports")
    require_string_list(platform.get("notes"), "platform.notes")
    load_rehearsal_gate_policies(catalog)

    services = require_mapping(catalog.get("services"), "services")
    service_catalog_index = load_service_catalog_index()
    if set(services) != set(service_catalog_index):
        missing = sorted(set(service_catalog_index) - set(services))
        extra = sorted(set(services) - set(service_catalog_index))
        details = []
        if missing:
            details.append(f"missing services: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected services: {', '.join(extra)}")
        raise ValueError("service redundancy catalog must match the service capability catalog: " + "; ".join(details))

    allowed_locations = known_locations()
    for service_id, entry in services.items():
        entry = require_mapping(entry, f"services.{service_id}")
        tier = require_enum(entry.get("tier"), f"services.{service_id}.tier", set(TIER_ORDER))

        recovery_objective = require_mapping(
            entry.get("recovery_objective"),
            f"services.{service_id}.recovery_objective",
        )
        require_int(
            recovery_objective.get("rto_minutes"),
            f"services.{service_id}.recovery_objective.rto_minutes",
            minimum=1,
        )
        require_int(
            recovery_objective.get("rpo_minutes"),
            f"services.{service_id}.recovery_objective.rpo_minutes",
            minimum=0,
        )

        require_string_list(entry.get("backup_sources"), f"services.{service_id}.backup_sources")
        standby = require_mapping(entry.get("standby"), f"services.{service_id}.standby")
        standby_kind = require_enum(
            standby.get("kind"),
            f"services.{service_id}.standby.kind",
            {"none", "cold", "warm", "active"},
        )
        expected_kind = STANDBY_KIND_BY_TIER[tier]
        if standby_kind != expected_kind:
            raise ValueError(f"services.{service_id}.standby.kind must be {expected_kind!r} for tier {tier}")

        location = require_str(standby.get("location"), f"services.{service_id}.standby.location")
        require_str(
            standby.get("failover_trigger"),
            f"services.{service_id}.standby.failover_trigger",
        )
        require_str(
            standby.get("failback_method"),
            f"services.{service_id}.standby.failback_method",
        )
        if standby_kind == "none":
            if location.lower() not in KNOWN_EMPTY_LOCATIONS:
                raise ValueError(
                    f"services.{service_id}.standby.location must describe an empty standby location for tier {tier}"
                )
        elif location not in allowed_locations:
            raise ValueError(f"services.{service_id}.standby.location must reference a known host or guest location")
        normalized_rehearsal_metadata(catalog, service_id, entry)


def build_live_apply_plan(
    catalog: dict[str, Any],
    *,
    service_id: str | None = None,
    allow_fallback: bool = False,
) -> list[dict[str, str]]:
    services = require_mapping(catalog.get("services"), "services")
    service_index = load_service_catalog_index()
    if service_id:
        canonical_service_id = resolve_service_id(service_id)
        if canonical_service_id not in services:
            raise ValueError(f"unknown service: {service_id}")
        target_ids = [canonical_service_id]
    else:
        target_ids = active_service_ids(service_index)

    platform = require_mapping(catalog.get("platform"), "platform")
    platform_max_tier = require_enum(
        platform.get("max_supported_tier"),
        "platform.max_supported_tier",
        set(TIER_ORDER),
    )

    plans: list[dict[str, str]] = []
    for current_service_id in target_ids:
        entry = require_mapping(services[current_service_id], f"services.{current_service_id}")
        declared_tier = require_enum(
            entry.get("tier"),
            f"services.{current_service_id}.tier",
            set(TIER_ORDER),
        )
        effective = effective_tier(
            declared_tier,
            platform_max_tier,
            allow_fallback=allow_fallback,
        )
        rehearsal_gate = evaluate_rehearsal_gate(catalog, current_service_id)
        standby = require_mapping(entry.get("standby"), f"services.{current_service_id}.standby")
        plans.append(
            {
                "service_id": current_service_id,
                "declared_tier": declared_tier,
                "effective_tier": effective,
                "implemented_tier": rehearsal_gate["implemented_tier"],
                "rehearsal_gate_status": rehearsal_gate["status"],
                "rehearsal_summary": rehearsal_gate["summary"],
                "live_apply_mode": LIVE_APPLY_MODE_BY_TIER[effective],
                "standby_kind": require_str(standby.get("kind"), f"services.{current_service_id}.standby.kind"),
                "standby_location": require_str(
                    standby.get("location"),
                    f"services.{current_service_id}.standby.location",
                ),
            }
        )
    return plans


def list_services(catalog: dict[str, Any]) -> int:
    service_catalog_index = load_service_catalog_index()
    print(f"Service redundancy catalog: {SERVICE_REDUNDANCY_PATH}")
    print("Available services:")
    for service_id, entry in sorted(require_mapping(catalog.get("services"), "services").items()):
        entry = require_mapping(entry, f"services.{service_id}")
        service_name = service_catalog_index[service_id]["name"]
        rehearsal_gate = evaluate_rehearsal_gate(catalog, service_id)
        print(
            f"  - {service_id} [{service_name}] "
            f"declared={entry['tier']} implemented={rehearsal_gate['implemented_tier']} "
            f"gate={rehearsal_gate['status']} standby={entry['standby']['kind']} "
            f"location={entry['standby']['location']}"
        )
    return 0


def show_service(catalog: dict[str, Any], service_id: str) -> int:
    canonical_service_id = resolve_service_id(service_id)
    services = require_mapping(catalog.get("services"), "services")
    if canonical_service_id not in services:
        print(f"Unknown service: {service_id}", file=sys.stderr)
        return 2

    service_catalog_index = load_service_catalog_index()
    entry = require_mapping(services[canonical_service_id], f"services.{canonical_service_id}")
    standby = require_mapping(entry.get("standby"), f"services.{canonical_service_id}.standby")
    recovery_objective = require_mapping(
        entry.get("recovery_objective"),
        f"services.{canonical_service_id}.recovery_objective",
    )
    rehearsal_gate = evaluate_rehearsal_gate(catalog, canonical_service_id)
    print(f"Service: {canonical_service_id}")
    print(f"Name: {service_catalog_index[canonical_service_id]['name']}")
    print(f"Declared Tier: {entry['tier']}")
    print(f"Implemented Tier: {rehearsal_gate['implemented_tier']}")
    print(f"Rehearsal Gate: {rehearsal_gate['status']}")
    print(f"Rehearsal Summary: {rehearsal_gate['summary']}")
    print(f"Recovery Objective: RTO {recovery_objective['rto_minutes']}m / RPO {recovery_objective['rpo_minutes']}m")
    print("Backup Sources:")
    for backup_source in entry["backup_sources"]:
        print(f"  - {backup_source}")
    print(f"Standby Kind: {standby['kind']}")
    print(f"Standby Location: {standby['location']}")
    print(f"Failover Trigger: {standby['failover_trigger']}")
    print(f"Failback Method: {standby['failback_method']}")
    if rehearsal_gate["required_policies"]:
        print("Required Rehearsals:")
        for policy in rehearsal_gate["required_policies"]:
            print(f"  - {policy['tier']}: {policy['exercise']} within {policy['freshness_window_days']}d")
    if rehearsal_gate["proofs"]:
        print("Recorded Proofs:")
        for proof in rehearsal_gate["proofs"]:
            print(
                f"  - {proof['performed_on'].isoformat()} {proof['proves_tier']} "
                f"{proof['result']} target={proof['target_environment']} "
                f"duration={proof['duration_minutes']}m "
                f"rto={proof['observed_rto_seconds']}s "
                f"evidence={proof['evidence_ref']}"
            )
    if "notes" in entry:
        print(f"Notes: {entry['notes']}")
    return 0


def check_live_apply(
    catalog: dict[str, Any],
    *,
    service_id: str | None,
    allow_fallback: bool,
) -> int:
    plans = build_live_apply_plan(
        catalog,
        service_id=service_id,
        allow_fallback=allow_fallback,
    )
    for plan in plans:
        print(
            f"{plan['service_id']}: declared {plan['declared_tier']} -> "
            f"platform {plan['effective_tier']} -> implemented {plan['implemented_tier']} "
            f"[gate={plan['rehearsal_gate_status']}] ({plan['live_apply_mode']}) "
            f"standby={plan['standby_kind']}@{plan['standby_location']}"
        )
        print(f"  rehearsal: {plan['rehearsal_summary']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate the service redundancy tier catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the catalog and exit.")
    parser.add_argument("--list", action="store_true", help="List all services and their redundancy tiers.")
    parser.add_argument("--service", help="Show one service entry.")
    parser.add_argument(
        "--check-live-apply",
        action="store_true",
        help="Validate the catalog and render the live-apply interpretation.",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow declared tiers to fall back to the platform-supported tier instead of failing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog = load_redundancy_catalog()
        validate_redundancy_catalog(catalog)
        if args.validate:
            print(f"Service redundancy catalog OK: {SERVICE_REDUNDANCY_PATH}")
            return 0
        if args.check_live_apply:
            return check_live_apply(
                catalog,
                service_id=args.service,
                allow_fallback=args.allow_fallback,
            )
        if args.service:
            return show_service(catalog, args.service)
        return list_services(catalog)
    except Exception as exc:
        return emit_cli_error("Service redundancy catalog", exc)


if __name__ == "__main__":
    raise SystemExit(main())
