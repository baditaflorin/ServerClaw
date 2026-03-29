#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from controller_automation_toolkit import emit_cli_error, load_json, repo_path

try:
    from scripts.deployment_history import (
        build_service_matchers,
        infer_service_ids,
        parse_timestamp,
        receipt_environment,
    )
except ImportError:  # pragma: no cover - packaged/runtime fallback
    from deployment_history import build_service_matchers, infer_service_ids, parse_timestamp, receipt_environment

try:
    from scripts.environment_catalog import active_environment_ids
except ImportError:  # pragma: no cover - packaged/runtime fallback
    from environment_catalog import active_environment_ids

try:
    from scripts.publication_contract import registry_entries
except ImportError:  # pragma: no cover - packaged/runtime fallback
    from publication_contract import registry_entries

from platform.health import HealthCompositeClient


CATALOG_PATH = repo_path("config", "runtime-assurance-matrix.json")
SCHEMA_PATH = repo_path("docs", "schema", "runtime-assurance-matrix.schema.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
ENVIRONMENT_TOPOLOGY_PATH = repo_path("config", "environment-topology.json")
PUBLICATION_REGISTRY_PATH = repo_path("config", "subdomain-exposure-registry.json")
LIVE_APPLY_DIR = repo_path("receipts", "live-applies")

ALLOWED_CLASSES = {"required", "best_effort", "n_a"}
STATUS_ORDER = {"failed": 0, "degraded": 1, "unknown": 2, "pass": 3, "n_a": 4}
DIMENSION_IDS = (
    "declared_runtime",
    "health",
    "route",
    "tls",
    "smoke",
    "browser_journey",
    "log_queryability",
)
BROWSER_KEYWORDS = ("browser", "oauth2", "playwright", "sign in", "login", "logout")
LOG_KEYWORDS = ("grafana logs", "loki", "log query", "query logs", "dozzle", "log canary")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def isoformat(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def active_environment_ids_from_payload(environment_topology: dict[str, Any]) -> tuple[str, ...]:
    environment_ids: list[str] = []
    for item in environment_topology.get("environments", []):
        if not isinstance(item, dict):
            continue
        if item.get("status") != "active":
            continue
        environment_id = item.get("id")
        if isinstance(environment_id, str) and environment_id.strip():
            environment_ids.append(environment_id)
    if environment_ids:
        return tuple(environment_ids)
    return active_environment_ids()


def load_runtime_assurance_catalog(path: Path | None = None) -> dict[str, Any]:
    payload = load_json(path or CATALOG_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{path or CATALOG_PATH} must be an object")
    return payload


def load_service_catalog(path: Path | None = None) -> dict[str, Any]:
    payload = load_json(path or SERVICE_CATALOG_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{path or SERVICE_CATALOG_PATH} must be an object")
    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError(f"{path or SERVICE_CATALOG_PATH} must define a services list")
    return payload


def load_environment_topology(path: Path | None = None) -> dict[str, Any]:
    payload = load_json(path or ENVIRONMENT_TOPOLOGY_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{path or ENVIRONMENT_TOPOLOGY_PATH} must be an object")
    return payload


def load_publication_registry(path: Path | None = None) -> dict[str, Any]:
    payload = load_json(path or PUBLICATION_REGISTRY_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{path or PUBLICATION_REGISTRY_PATH} must be an object")
    return payload


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def validate_runtime_assurance_catalog(
    catalog: dict[str, Any],
    *,
    service_catalog: dict[str, Any] | None = None,
    environment_topology: dict[str, Any] | None = None,
    schema_path: Path | None = None,
) -> None:
    try:
        import jsonschema
    except ModuleNotFoundError:
        jsonschema = None  # type: ignore[assignment]

    if jsonschema is not None:
        jsonschema.validate(instance=catalog, schema=load_json(schema_path or SCHEMA_PATH))

    require_string(catalog.get("schema_version"), "runtime-assurance.schema_version")
    dimensions = require_mapping(catalog.get("dimensions"), "runtime-assurance.dimensions")
    profiles = require_mapping(catalog.get("profiles"), "runtime-assurance.profiles")
    default_profile_by_exposure = require_mapping(
        catalog.get("default_profile_by_exposure"),
        "runtime-assurance.default_profile_by_exposure",
    )

    if set(dimensions) != set(DIMENSION_IDS):
        raise ValueError(
            "runtime-assurance.dimensions must define exactly "
            + ", ".join(DIMENSION_IDS)
        )

    for dimension_id, dimension in dimensions.items():
        dimension = require_mapping(dimension, f"runtime-assurance.dimensions.{dimension_id}")
        require_string(dimension.get("title"), f"runtime-assurance.dimensions.{dimension_id}.title")
        require_string(
            dimension.get("description"),
            f"runtime-assurance.dimensions.{dimension_id}.description",
        )

    for profile_id, profile in profiles.items():
        profile = require_mapping(profile, f"runtime-assurance.profiles.{profile_id}")
        require_string(profile.get("title"), f"runtime-assurance.profiles.{profile_id}.title")
        require_string(profile.get("description"), f"runtime-assurance.profiles.{profile_id}.description")
        classes = require_mapping(
            profile.get("dimension_classes"),
            f"runtime-assurance.profiles.{profile_id}.dimension_classes",
        )
        if set(classes) != set(dimensions):
            raise ValueError(
                f"runtime-assurance.profiles.{profile_id}.dimension_classes must cover exactly {sorted(dimensions)}"
            )
        for dimension_id, assurance_class in classes.items():
            assurance_class = require_string(
                assurance_class,
                f"runtime-assurance.profiles.{profile_id}.dimension_classes.{dimension_id}",
            )
            if assurance_class not in ALLOWED_CLASSES:
                raise ValueError(
                    f"runtime-assurance.profiles.{profile_id}.dimension_classes.{dimension_id} must be one of {sorted(ALLOWED_CLASSES)}"
                )

    for exposure in ("edge-published", "edge-static", "informational-only", "private-only"):
        profile_id = require_string(
            default_profile_by_exposure.get(exposure),
            f"runtime-assurance.default_profile_by_exposure.{exposure}",
        )
        if profile_id not in profiles:
            raise ValueError(
                f"runtime-assurance.default_profile_by_exposure.{exposure} references unknown profile '{profile_id}'"
            )

    for service_id, override in require_mapping(
        catalog.get("service_overrides", {}),
        "runtime-assurance.service_overrides",
    ).items():
        override = require_mapping(override, f"runtime-assurance.service_overrides.{service_id}")
        profile_id = require_string(override.get("profile"), f"runtime-assurance.service_overrides.{service_id}.profile")
        if profile_id not in profiles:
            raise ValueError(f"runtime-assurance.service_overrides.{service_id}.profile references unknown profile '{profile_id}'")

    freshness = require_mapping(
        catalog.get("freshness_days_by_dimension", {}),
        "runtime-assurance.freshness_days_by_dimension",
    )
    for dimension_id, days in freshness.items():
        if dimension_id not in dimensions:
            raise ValueError(
                f"runtime-assurance.freshness_days_by_dimension.{dimension_id} must reference a declared dimension"
            )
        if isinstance(days, bool) or not isinstance(days, int) or days < 1:
            raise ValueError(f"runtime-assurance.freshness_days_by_dimension.{dimension_id} must be an integer >= 1")

    service_catalog = service_catalog or load_service_catalog()
    environment_topology = environment_topology or load_environment_topology()
    active_envs = set(active_environment_ids_from_payload(environment_topology))

    for service in service_catalog.get("services", []):
        if not isinstance(service, dict) or service.get("lifecycle_status") != "active":
            continue
        service_id = require_string(service.get("id"), "service.id")
        exposure = require_string(service.get("exposure"), f"service.{service_id}.exposure")
        if exposure not in default_profile_by_exposure:
            raise ValueError(f"runtime-assurance.default_profile_by_exposure is missing exposure '{exposure}'")
        profile_id = resolve_profile_id(service, catalog)
        if profile_id not in profiles:
            raise ValueError(f"service {service_id} resolves to unknown profile '{profile_id}'")
        environments = require_mapping(service.get("environments"), f"service.{service_id}.environments")
        for environment_id, binding in environments.items():
            binding = require_mapping(binding, f"service.{service_id}.environments.{environment_id}")
            status = require_string(binding.get("status"), f"service.{service_id}.environments.{environment_id}.status")
            if status == "active" and environment_id not in active_envs:
                raise ValueError(
                    f"service {service_id} declares active environment '{environment_id}' outside the active environment topology"
                )


def resolve_profile_id(service: dict[str, Any], catalog: dict[str, Any]) -> str:
    service_id = str(service.get("id", ""))
    overrides = catalog.get("service_overrides", {})
    if isinstance(overrides, dict):
        override = overrides.get(service_id)
        if isinstance(override, dict) and isinstance(override.get("profile"), str):
            return override["profile"]
    exposure = str(service.get("exposure", ""))
    defaults = catalog.get("default_profile_by_exposure", {})
    if isinstance(defaults, dict) and isinstance(defaults.get(exposure), str):
        return defaults[exposure]
    raise ValueError(f"service {service_id} does not resolve to a runtime assurance profile")


def load_health_payload(repo_root: Path) -> dict[str, Any]:
    dsn = (
        os_environ("LV3_GATEWAY_WORLD_STATE_DSN")
        or os_environ("WORLD_STATE_DSN")
        or os_environ("LV3_GATEWAY_GRAPH_DSN")
        or os_environ("LV3_GRAPH_DSN")
    )
    client = HealthCompositeClient(
        repo_root=repo_root,
        dsn=dsn,
        world_state_dsn=dsn,
        ledger_dsn=dsn,
    )
    return {
        "services": [entry.as_dict(now=utc_now()) for entry in client.get_all(allow_stale=True)],
        "source": "health_composite",
    }


def os_environ(name: str) -> str | None:
    value = __import__("os").environ.get(name, "").strip()
    return value or None


def build_health_map(health_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    health_map: dict[str, dict[str, Any]] = {}
    for item in health_payload.get("services", []):
        if not isinstance(item, dict):
            continue
        service_id = item.get("service_id") or item.get("id")
        if not isinstance(service_id, str) or not service_id:
            continue
        health_map[service_id] = item
    return health_map


def collect_receipt_evidence(repo_root: Path, service_catalog: dict[str, Any]) -> list[dict[str, Any]]:
    matchers = build_service_matchers(service_catalog)
    receipts: list[dict[str, Any]] = []
    for path in sorted((repo_root / "receipts" / "live-applies").rglob("*.json"), reverse=True):
        relative_path = path.relative_to(repo_root)
        # Worktree syncs from macOS can leave AppleDouble sidecars like `._foo.json`.
        if any(part.startswith("._") for part in relative_path.parts) or relative_path.name == ".DS_Store":
            continue
        try:
            payload = load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        verification = payload.get("verification", [])
        notes = payload.get("notes", [])
        evidence_refs = payload.get("evidence_refs", [])
        text_parts = [
            str(payload.get("summary", "")),
            str(payload.get("workflow_id", "")),
            " ".join(str(item.get("check", "")) for item in verification if isinstance(item, dict)),
            " ".join(str(item.get("observed", "")) for item in verification if isinstance(item, dict)),
            " ".join(str(item) for item in notes if isinstance(item, str)),
            " ".join(str(item) for item in evidence_refs if isinstance(item, str)),
        ]
        service_ids = infer_service_ids(text_parts, matchers, adr=payload.get("adr"))
        results = [str(item.get("result", "")) for item in verification if isinstance(item, dict)]
        if any(result == "fail" for result in results):
            outcome = "failed"
        elif any(result == "partial" for result in results):
            outcome = "degraded"
        else:
            outcome = "pass"
        recorded_value = (
            payload.get("recorded_at")
            or payload.get("recorded_on")
            or payload.get("applied_on")
        )
        recorded_at = parse_timestamp(str(recorded_value), default_to_start_of_day=True) if recorded_value else None
        receipts.append(
            {
                "receipt_id": str(payload.get("receipt_id", path.stem)),
                "path": str(path.relative_to(repo_root).as_posix()),
                "environment": receipt_environment(path, repo_root / "receipts" / "live-applies"),
                "service_ids": service_ids,
                "outcome": outcome,
                "recorded_at": recorded_at,
                "search_text": f" {normalize_text(' '.join(text_parts))} ",
            }
        )
    return receipts


def receipt_for_dimension(
    receipts: list[dict[str, Any]],
    *,
    service_id: str,
    environment: str,
    keywords: tuple[str, ...] | None = None,
    max_age_days: int | None = None,
    now: dt.datetime,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for receipt in receipts:
        if service_id not in receipt.get("service_ids", []):
            continue
        if receipt.get("environment") != environment:
            continue
        if keywords:
            search_text = str(receipt.get("search_text", ""))
            if not any(f" {normalize_text(keyword)} " in search_text for keyword in keywords):
                continue
        recorded_at = receipt.get("recorded_at")
        if not isinstance(recorded_at, dt.datetime):
            continue
        if max_age_days is not None and recorded_at < (now - dt.timedelta(days=max_age_days)):
            continue
        if best is None or recorded_at > best["recorded_at"]:
            best = receipt
    return best


def active_publications_by_key(publication_registry: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    mapping: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for publication in registry_entries(publication_registry):
        if not isinstance(publication, dict) or publication.get("status") != "active":
            continue
        service_id = publication.get("service_id")
        environment = publication.get("environment")
        if not isinstance(service_id, str) or not isinstance(environment, str):
            continue
        mapping.setdefault((service_id, environment), []).append(publication)
    return mapping


def parse_url_metadata(value: str | None) -> dict[str, str | None]:
    if not isinstance(value, str) or not value.strip():
        return {"scheme": None, "hostname": None}
    parsed = urlparse(value)
    return {"scheme": parsed.scheme or None, "hostname": parsed.hostname or None}


def health_dimension_status(item: dict[str, Any]) -> tuple[str, str, str | None]:
    status = str(item.get("composite_status") or item.get("status") or "unknown").lower()
    reason = str(item.get("reason") or item.get("detail") or item.get("message") or "No health evidence.")
    computed_at = str(item.get("computed_at") or "") or None
    if status in {"healthy", "ok", "up", "pass"}:
        return "pass", reason, computed_at
    if status in {"degraded", "warning", "warn"}:
        return "degraded", reason, computed_at
    if status in {"critical", "down", "failed", "unreachable", "error"}:
        return "failed", reason, computed_at
    return "unknown", reason, computed_at


def declared_runtime_dimension(service: dict[str, Any], health_item: dict[str, Any] | None, receipt: dict[str, Any] | None) -> tuple[str, str, str | None]:
    if health_item:
        health_status, reason, last_verified = health_dimension_status(health_item)
        if health_status in {"pass", "degraded", "failed"}:
            return "pass", f"Runtime witness present through health composite: {reason}", last_verified
    if receipt is not None:
        recorded_at = receipt.get("recorded_at")
        return "pass", f"Recent governed receipt {receipt['receipt_id']} proves the service was applied and verified.", isoformat(recorded_at)
    return "unknown", "No current runtime witness was found in the health composite or recent live-apply receipts.", None


def route_dimension(
    *,
    service: dict[str, Any],
    binding: dict[str, Any],
    publications: list[dict[str, Any]],
    health_item: dict[str, Any] | None,
) -> tuple[str, str, str | None]:
    url = str(binding.get("url") or service.get("public_url") or service.get("internal_url") or "")
    url_meta = parse_url_metadata(url)
    health_status, _reason, last_verified = health_dimension_status(health_item or {})
    exposure = str(service.get("exposure") or "")

    if exposure == "private-only" and not publications:
        if not url_meta["hostname"]:
            return "unknown", "The private route is not declared in the service binding URL.", last_verified
        if health_status == "failed":
            return "failed", f"The private route host {url_meta['hostname']} is declared but the current health evidence is failing.", last_verified
        if health_status == "degraded":
            return "degraded", f"The private route host {url_meta['hostname']} is declared and reachable but degraded.", last_verified
        if health_status == "pass":
            return "pass", f"The private route host {url_meta['hostname']} is declared and currently reachable.", last_verified
        return "unknown", f"The private route host {url_meta['hostname']} is declared, but no fresh reachability evidence is available.", last_verified

    if not publications:
        return "failed", "The service requires a publication entry, but no active route was found in the publication registry.", last_verified

    expected_host = str(binding.get("subdomain") or url_meta["hostname"] or "")
    matching = [
        publication
        for publication in publications
        if not expected_host or publication.get("fqdn") == expected_host
    ]
    if expected_host and not matching:
        return "failed", f"The declared host {expected_host} does not match any active publication entry for this service and environment.", last_verified

    fqdn = str((matching or publications)[0].get("fqdn") or expected_host or "unknown")
    if health_status == "failed":
        return "failed", f"The route {fqdn} is declared, but the current health evidence shows the published path failing.", last_verified
    if health_status == "degraded":
        return "degraded", f"The route {fqdn} is declared and resolves to the correct surface, but the live path is degraded.", last_verified
    if health_status == "pass":
        return "pass", f"The active publication for {fqdn} matches the declared environment and is currently reachable.", last_verified
    return "unknown", f"The active publication for {fqdn} is declared, but no fresh live reachability evidence is available.", last_verified


def tls_dimension(
    *,
    service: dict[str, Any],
    binding: dict[str, Any],
    publications: list[dict[str, Any]],
    health_item: dict[str, Any] | None,
    assurance_class: str,
) -> tuple[str, str, str | None]:
    url = str(binding.get("url") or service.get("public_url") or service.get("internal_url") or "")
    url_meta = parse_url_metadata(url)
    publication_tls = any(isinstance(publication.get("adapter"), dict) and publication["adapter"].get("tls") for publication in publications)
    health_status, _reason, last_verified = health_dimension_status(health_item or {})

    if url_meta["scheme"] != "https" and not publication_tls:
        if assurance_class == "required":
            return "failed", "The profile requires TLS proof, but the declared surface is not HTTPS-bearing.", last_verified
        return "n_a", "The declared surface does not currently expose HTTPS, so TLS posture is not applicable to this binding.", last_verified

    if health_status == "failed":
        return "failed", "The HTTPS surface is declared, but the current live health evidence is failing.", last_verified
    if health_status == "degraded":
        return "degraded", "The HTTPS surface is declared and negotiates enough to answer probes, but the live path is degraded.", last_verified
    if health_status == "pass":
        return "pass", "The declared HTTPS surface is currently reachable and negotiating successfully on the live path.", last_verified
    return "unknown", "The surface is declared as HTTPS-bearing, but no fresh live TLS evidence is available.", last_verified


def receipt_dimension(
    *,
    dimension_id: str,
    service_id: str,
    environment: str,
    receipts: list[dict[str, Any]],
    freshness_days: int | None,
    now: dt.datetime,
) -> tuple[str, str, str | None]:
    keywords: tuple[str, ...] | None = None
    if dimension_id == "browser_journey":
        keywords = BROWSER_KEYWORDS
    elif dimension_id == "log_queryability":
        keywords = LOG_KEYWORDS

    receipt = receipt_for_dimension(
        receipts,
        service_id=service_id,
        environment=environment,
        keywords=keywords,
        max_age_days=freshness_days,
        now=now,
    )
    if receipt is None:
        if dimension_id == "log_queryability":
            return "unknown", "No recent receipt records log-ingestion or query-path proof for this service.", None
        if dimension_id == "browser_journey":
            return "unknown", "No recent receipt records a browser login and logout journey for this service.", None
        return "unknown", "No recent governed smoke receipt is available for this service and environment.", None
    recorded_at = receipt.get("recorded_at")
    if receipt["outcome"] == "pass":
        return "pass", f"Receipt {receipt['receipt_id']} contains recent {dimension_id.replace('_', ' ')} evidence.", isoformat(recorded_at)
    if receipt["outcome"] == "degraded":
        return "degraded", f"Receipt {receipt['receipt_id']} recorded a partial verification result for this dimension.", isoformat(recorded_at)
    return "failed", f"Receipt {receipt['receipt_id']} recorded a failed verification result for this dimension.", isoformat(recorded_at)


def evaluate_dimension(
    *,
    dimension_id: str,
    assurance_class: str,
    service: dict[str, Any],
    binding: dict[str, Any],
    health_item: dict[str, Any] | None,
    publications: list[dict[str, Any]],
    receipts: list[dict[str, Any]],
    freshness_days: dict[str, int],
    now: dt.datetime,
) -> dict[str, Any]:
    service_id = str(service.get("id"))
    environment = str(binding.get("environment_id"))

    if assurance_class == "n_a":
        return {
            "id": dimension_id,
            "class": assurance_class,
            "status": "n_a",
            "reason": "This dimension is not applicable to the resolved assurance profile.",
            "last_verified": None,
        }

    runtime_receipt = receipt_for_dimension(
        receipts,
        service_id=service_id,
        environment=environment,
        max_age_days=freshness_days.get("smoke"),
        now=now,
    )

    if dimension_id == "declared_runtime":
        status, reason, last_verified = declared_runtime_dimension(service, health_item, runtime_receipt)
    elif dimension_id == "health":
        status, reason, last_verified = health_dimension_status(health_item or {})
    elif dimension_id == "route":
        status, reason, last_verified = route_dimension(
            service=service,
            binding=binding,
            publications=publications,
            health_item=health_item,
        )
    elif dimension_id == "tls":
        status, reason, last_verified = tls_dimension(
            service=service,
            binding=binding,
            publications=publications,
            health_item=health_item,
            assurance_class=assurance_class,
        )
    elif dimension_id in {"smoke", "browser_journey", "log_queryability"}:
        status, reason, last_verified = receipt_dimension(
            dimension_id=dimension_id,
            service_id=service_id,
            environment=environment,
            receipts=receipts,
            freshness_days=freshness_days.get(dimension_id),
            now=now,
        )
    else:  # pragma: no cover - guarded by config validation
        status, reason, last_verified = "unknown", "Unsupported dimension.", None

    return {
        "id": dimension_id,
        "class": assurance_class,
        "status": status,
        "reason": reason,
        "last_verified": last_verified,
    }


def overall_status(dimensions: list[dict[str, Any]]) -> str:
    required = [item["status"] for item in dimensions if item["class"] == "required"]
    if any(status == "failed" for status in required):
        return "failed"
    if any(status == "degraded" for status in required):
        return "degraded"
    if any(status == "unknown" for status in required):
        return "unknown"
    return "pass"


def summarize_dimensions(dimensions: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"required": 0, "best_effort": 0, "n_a": 0, "pass": 0, "degraded": 0, "failed": 0, "unknown": 0}
    for item in dimensions:
        summary[item["class"]] += 1
        if item["status"] in summary:
            summary[item["status"]] += 1
    return summary


def active_service_environment_bindings(
    service_catalog: dict[str, Any],
    environment_topology: dict[str, Any],
) -> list[dict[str, Any]]:
    active_envs = set(active_environment_ids_from_payload(environment_topology))
    bindings: list[dict[str, Any]] = []
    for service in service_catalog.get("services", []):
        if not isinstance(service, dict) or service.get("lifecycle_status") != "active":
            continue
        for environment_id, binding in service.get("environments", {}).items():
            if not isinstance(binding, dict) or binding.get("status") != "active":
                continue
            if environment_id not in active_envs:
                continue
            item = dict(binding)
            item["environment_id"] = environment_id
            bindings.append({"service": service, "binding": item})
    bindings.sort(key=lambda item: (str(item["binding"]["environment_id"]), str(item["service"]["id"])))
    return bindings


def build_runtime_assurance_report(
    *,
    repo_root: Path | None = None,
    catalog: dict[str, Any] | None = None,
    service_catalog: dict[str, Any] | None = None,
    environment_topology: dict[str, Any] | None = None,
    publication_registry: dict[str, Any] | None = None,
    health_payload: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    repo_root = repo_root or repo_path()
    observed_now = now or utc_now()
    catalog = catalog or load_runtime_assurance_catalog(repo_root / "config" / "runtime-assurance-matrix.json")
    service_catalog = service_catalog or load_service_catalog(repo_root / "config" / "service-capability-catalog.json")
    environment_topology = environment_topology or load_environment_topology(repo_root / "config" / "environment-topology.json")
    publication_registry = publication_registry or load_publication_registry(repo_root / "config" / "subdomain-exposure-registry.json")
    validate_runtime_assurance_catalog(catalog, service_catalog=service_catalog, environment_topology=environment_topology)
    health_payload = health_payload or load_health_payload(repo_root)
    health_map = build_health_map(health_payload)
    publications_by_key = active_publications_by_key(publication_registry)
    receipts = collect_receipt_evidence(repo_root, service_catalog)
    freshness_days = {
        key: int(value)
        for key, value in require_mapping(
            catalog.get("freshness_days_by_dimension", {}),
            "runtime-assurance.freshness_days_by_dimension",
        ).items()
    }

    entries: list[dict[str, Any]] = []
    profiles = require_mapping(catalog.get("profiles"), "runtime-assurance.profiles")
    dimensions_meta = require_mapping(catalog.get("dimensions"), "runtime-assurance.dimensions")
    for item in active_service_environment_bindings(service_catalog, environment_topology):
        service = item["service"]
        binding = item["binding"]
        service_id = str(service["id"])
        environment_id = str(binding["environment_id"])
        profile_id = resolve_profile_id(service, catalog)
        profile = require_mapping(profiles[profile_id], f"runtime-assurance.profiles.{profile_id}")
        publications = publications_by_key.get((service_id, environment_id), [])
        health_item = health_map.get(service_id)
        dimension_entries: list[dict[str, Any]] = []
        for dimension_id in DIMENSION_IDS:
            dimension = evaluate_dimension(
                dimension_id=dimension_id,
                assurance_class=str(profile["dimension_classes"][dimension_id]),
                service=service,
                binding=binding,
                health_item=health_item,
                publications=publications,
                receipts=receipts,
                freshness_days=freshness_days,
                now=observed_now,
            )
            dimension["title"] = dimensions_meta[dimension_id]["title"]
            dimension_entries.append(dimension)

        entry = {
            "service_id": service_id,
            "service_name": str(service.get("name", service_id)),
            "environment": environment_id,
            "profile_id": profile_id,
            "profile_title": str(profile.get("title", profile_id)),
            "overall_status": overall_status(dimension_entries),
            "summary": summarize_dimensions(dimension_entries),
            "vm": service.get("vm"),
            "vmid": service.get("vmid"),
            "runbook": service.get("runbook"),
            "adr": service.get("adr"),
            "exposure": service.get("exposure"),
            "primary_url": binding.get("url") or service.get("public_url") or service.get("internal_url"),
            "publications": [
                {
                    "fqdn": publication.get("fqdn"),
                    "delivery_model": publication.get("publication", {}).get("delivery_model"),
                    "access_model": publication.get("publication", {}).get("access_model"),
                    "audience": publication.get("publication", {}).get("audience"),
                }
                for publication in publications
            ],
            "dimensions": dimension_entries,
        }
        entries.append(entry)

    summary = {"total": len(entries), "pass": 0, "degraded": 0, "failed": 0, "unknown": 0}
    for entry in entries:
        summary[entry["overall_status"]] += 1

    return {
        "generated_at": isoformat(observed_now),
        "summary": summary,
        "entries": entries,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate or render the runtime assurance matrix.")
    parser.add_argument("--validate", action="store_true", help="Validate the runtime assurance catalog.")
    parser.add_argument(
        "--print-report-json",
        action="store_true",
        help="Render the runtime assurance report as JSON.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_path(),
        help="Repository root used to resolve catalog paths.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.validate and not args.print_report_json:
        raise ValueError("choose at least one of --validate or --print-report-json")

    repo_root = args.repo_root.resolve()
    catalog = load_runtime_assurance_catalog(repo_root / "config" / "runtime-assurance-matrix.json")
    service_catalog = load_service_catalog(repo_root / "config" / "service-capability-catalog.json")
    environment_topology = load_environment_topology(repo_root / "config" / "environment-topology.json")

    if args.validate:
        validate_runtime_assurance_catalog(
            catalog,
            service_catalog=service_catalog,
            environment_topology=environment_topology,
            schema_path=repo_root / "docs" / "schema" / "runtime-assurance-matrix.schema.json",
        )
        print(f"Runtime assurance matrix OK: {repo_root / 'config' / 'runtime-assurance-matrix.json'}")

    if args.print_report_json:
        report = build_runtime_assurance_report(
            repo_root=repo_root,
            catalog=catalog,
            service_catalog=service_catalog,
            environment_topology=environment_topology,
        )
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        emit_cli_error(str(exc))
