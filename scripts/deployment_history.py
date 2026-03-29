#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import json
import os
import importlib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json, repo_path
from changelog_redaction import redact_history_entries
from environment_catalog import receipt_subdirectory_environments
from mutation_audit import resolve_loki_url


LIVE_APPLY_DIR = repo_path("receipts", "live-applies")
PROMOTIONS_DIR = repo_path("receipts", "promotions")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
DEFAULT_MUTATION_AUDIT_LABEL = '{job="mutation-audit"}'
DEFAULT_AUDIT_LOOKBACK_DAYS = 90
DEFAULT_AUDIT_QUERY_LIMIT = 500
MUTATION_AUDIT_QUERY_URL_ENV = "LV3_MUTATION_AUDIT_LOKI_QUERY_URL"
MUTATION_AUDIT_QUERY_FILE_ENV = "LV3_MUTATION_AUDIT_QUERY_FILE"

@dataclass(frozen=True)
class ServiceMatcher:
    service_id: str
    name: str
    adr: str | None
    runbook: str | None
    keywords: tuple[str, ...]


def load_service_catalog_data() -> dict[str, Any]:
    catalog = load_json(SERVICE_CATALOG_PATH)
    try:
        module = importlib.import_module("service_catalog")
    except (ImportError, RuntimeError):
        return catalog

    validator = getattr(module, "validate_service_catalog", None)
    if callable(validator):
        validator(catalog)
    return catalog


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_timestamp(value: str | None, *, default_to_start_of_day: bool = False) -> dt.datetime:
    if not value:
        raise ValueError("timestamp value is required")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        parsed_date = dt.date.fromisoformat(value)
        hour = 0 if default_to_start_of_day else 12
        return dt.datetime.combine(parsed_date, dt.time(hour=hour, tzinfo=dt.timezone.utc))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def timestamp_to_iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify_value(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def actor_class_for_identity(actor_id: str | None) -> str:
    identity = (actor_id or "").strip().lower()
    if identity in {"codex", "claude", "automation", "ci"}:
        return "agent"
    if identity.startswith("ops"):
        return "operator"
    return "automation" if identity else "unknown"


def build_service_matchers(service_catalog: dict[str, Any] | None = None) -> dict[str, ServiceMatcher]:
    if service_catalog is None:
        service_catalog = load_service_catalog_data()

    matchers: dict[str, ServiceMatcher] = {}
    for service in service_catalog["services"]:
        keywords: set[str] = {
            normalize_text(service["id"]),
            normalize_text(service["name"]),
        }
        for field in ("vm", "subdomain", "public_url", "internal_url"):
            value = service.get(field)
            if isinstance(value, str) and value.strip():
                keywords.add(normalize_text(value))
        for tag in service.get("tags", []):
            if isinstance(tag, str) and tag.strip():
                keywords.add(normalize_text(tag))

        service_id_token = normalize_text(service["id"].replace("_", " "))
        if service_id_token:
            keywords.add(service_id_token)

        matchers[service["id"]] = ServiceMatcher(
            service_id=service["id"],
            name=service["name"],
            adr=service.get("adr"),
            runbook=service.get("runbook"),
            keywords=tuple(sorted(item for item in keywords if item)),
        )
    return matchers


def infer_service_ids(text_parts: list[str], matchers: dict[str, ServiceMatcher], adr: str | None = None) -> list[str]:
    haystack = normalize_text(" ".join(part for part in text_parts if part))
    service_ids = []
    for service_id, matcher in matchers.items():
        if adr and matcher.adr == adr:
            service_ids.append(service_id)
            continue
        for keyword in matcher.keywords:
            if keyword and keyword in haystack:
                service_ids.append(service_id)
                break
    return sorted(set(service_ids))


def render_services(service_ids: list[str], matchers: dict[str, ServiceMatcher]) -> list[str]:
    return [matchers[service_id].name for service_id in service_ids if service_id in matchers]


def iter_json_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.json") if path.is_file())


def relative_repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_path()).as_posix()
    except ValueError:
        return str(resolved)


def receipt_environment(path: Path, root: Path) -> str:
    relative = path.resolve().relative_to(root.resolve())
    if relative.parts and relative.parts[0] in receipt_subdirectory_environments():
        return relative.parts[0]
    return "production"


def receipt_outcome(receipt: dict[str, Any]) -> str:
    results = [item.get("result") for item in receipt.get("verification", []) if isinstance(item, dict)]
    if any(result == "fail" for result in results):
        return "failure"
    if any(result == "partial" for result in results):
        return "partial"
    return "success"


def history_receipt_id(path: Path, payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    receipt_id = payload.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        return None
    if path.stem != receipt_id:
        return None
    return receipt_id


def history_receipt_timestamp(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for field in ("recorded_on", "applied_on"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return None


def collect_live_apply_entries(
    *,
    receipts_dir: Path = LIVE_APPLY_DIR,
    service_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    matchers = build_service_matchers(service_catalog)
    entries: list[dict[str, Any]] = []
    for path in iter_json_paths(receipts_dir):
        receipt = load_json(path)
        receipt_id = history_receipt_id(path, receipt)
        receipt_timestamp = history_receipt_timestamp(receipt)
        if receipt_id is None or receipt_timestamp is None:
            continue
        timestamp = parse_timestamp(receipt_timestamp, default_to_start_of_day=True)
        targets = receipt.get("targets", [])
        target_labels = [
            f"{target.get('kind', 'unknown')}:{target.get('name', 'unknown')}"
            for target in targets
            if isinstance(target, dict)
        ]
        vm_names = sorted(
            {
                target["name"]
                for target in targets
                if isinstance(target, dict) and target.get("kind") == "vm" and target.get("name")
            }
        )
        text_parts = [
            receipt.get("summary", ""),
            " ".join(target_labels),
            " ".join(str(item.get("check", "")) for item in receipt.get("verification", []) if isinstance(item, dict)),
            " ".join(str(item.get("observed", "")) for item in receipt.get("verification", []) if isinstance(item, dict)),
            " ".join(str(note) for note in receipt.get("notes", [])),
            " ".join(str(ref) for ref in receipt.get("evidence_refs", [])),
        ]
        service_ids = infer_service_ids(text_parts, matchers, adr=receipt.get("adr"))
        environment = receipt_environment(path, receipts_dir)
        entries.append(
            {
                "id": receipt_id,
                "change_type": "live-apply",
                "timestamp": timestamp_to_iso(timestamp),
                "timestamp_precision": "date",
                "date_label": timestamp.date().isoformat(),
                "actor": receipt.get("recorded_by", "unknown"),
                "actor_class": actor_class_for_identity(receipt.get("recorded_by")),
                "environment": environment,
                "outcome": receipt_outcome(receipt),
                "service_ids": service_ids,
                "service_names": render_services(service_ids, matchers),
                "vm_names": vm_names,
                "targets": target_labels,
                "summary": receipt.get("summary", ""),
                "link_path": relative_repo_path(path),
                "source": "live_apply_receipt",
                "workflow_id": receipt.get("workflow_id"),
                "adr": receipt.get("adr"),
                "metadata": {
                    "repo_version_context": receipt.get("repo_version_context"),
                    "applied_on": receipt.get("applied_on"),
                    "recorded_on": receipt.get("recorded_on"),
                },
            }
        )
    return entries


def load_receipt_if_present(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return load_json(path)


def collect_promotion_entries(
    *,
    promotions_dir: Path = PROMOTIONS_DIR,
    receipts_dir: Path = LIVE_APPLY_DIR,
    service_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    matchers = build_service_matchers(service_catalog)
    entries: list[dict[str, Any]] = []
    for path in iter_json_paths(promotions_dir):
        receipt = load_json(path)
        timestamp = parse_timestamp(receipt.get("ts"), default_to_start_of_day=False)
        service_ids: list[str] = []
        referenced_receipts = []
        for key in ("staging_receipt", "prod_receipt"):
            value = receipt.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            referenced_receipts.append(value)
            candidate = repo_path(value)
            payload = load_receipt_if_present(candidate)
            if payload is None and not candidate.is_file():
                candidate = receipts_dir / Path(value).name
                payload = load_receipt_if_present(candidate)
            if payload is None:
                continue
            service_ids.extend(
                infer_service_ids(
                    [
                        payload.get("summary", ""),
                        " ".join(str(note) for note in payload.get("notes", [])),
                    ],
                    matchers,
                    adr=payload.get("adr"),
                )
            )

        text_parts = [
            receipt.get("branch", ""),
            receipt.get("playbook", ""),
            json.dumps(receipt.get("staging_health_check", {}), sort_keys=True),
            json.dumps(receipt.get("gate_actor", {}), sort_keys=True),
        ]
        service_ids.extend(infer_service_ids(text_parts, matchers))
        service_ids = sorted(set(service_ids))
        actor = ""
        if isinstance(receipt.get("gate_actor"), dict):
            actor = str(receipt["gate_actor"].get("id", ""))
        actor = actor or "promotion-gate"
        checks = receipt.get("staging_health_check", {})
        duration = checks.get("duration") if isinstance(checks, dict) else None
        title_parts = [f"Promoted {receipt.get('branch', 'unknown branch')}"]
        if receipt.get("playbook"):
            title_parts.append(f"via {receipt['playbook']}")
        summary = " ".join(title_parts)
        if receipt.get("gate_decision"):
            summary += f"; gate {receipt['gate_decision']}"
        entries.append(
            {
                "id": receipt.get("promotion_id", path.stem),
                "change_type": "promotion",
                "timestamp": timestamp_to_iso(timestamp),
                "timestamp_precision": "datetime",
                "date_label": timestamp.strftime("%Y-%m-%d %H:%M UTC"),
                "actor": actor,
                "actor_class": actor_class_for_identity(actor),
                "environment": "production",
                "outcome": "success" if receipt.get("gate_decision") == "approved" else "partial",
                "service_ids": service_ids,
                "service_names": render_services(service_ids, matchers),
                "vm_names": [],
                "targets": referenced_receipts,
                "summary": summary,
                "link_path": relative_repo_path(path),
                "source": "promotion_receipt",
                "workflow_id": "deploy-and-promote",
                "adr": "0073",
                "metadata": {
                    "branch": receipt.get("branch"),
                    "playbook": receipt.get("playbook"),
                    "staging_receipt": receipt.get("staging_receipt"),
                    "prod_receipt": receipt.get("prod_receipt"),
                    "staging_validation_duration": duration,
                    "gate_decision": receipt.get("gate_decision"),
                    "bypass_reason": receipt.get("bypass_reason"),
                },
            }
        )
    return entries


def resolve_mutation_audit_query_url(loki_query_url: str | None = None) -> str | None:
    candidate = loki_query_url or os.environ.get(MUTATION_AUDIT_QUERY_URL_ENV)
    if candidate:
        candidate = candidate.strip()
        if candidate.lower() == "off":
            return None
        return candidate

    push_url = resolve_loki_url()
    if not push_url:
        return None
    if push_url.endswith("/push"):
        return push_url.removesuffix("/push") + "/query_range"
    return push_url


def query_loki_mutation_audit(
    *,
    lookback_days: int,
    limit: int = DEFAULT_AUDIT_QUERY_LIMIT,
    loki_query_url: str | None = None,
) -> list[dict[str, Any]]:
    query_url = resolve_mutation_audit_query_url(loki_query_url)
    if not query_url:
        raise RuntimeError("mutation audit Loki query URL is not configured")

    end = utc_now()
    start = end - dt.timedelta(days=lookback_days)
    params = urllib.parse.urlencode(
        {
            "query": DEFAULT_MUTATION_AUDIT_LABEL,
            "start": str(int(start.timestamp() * 1_000_000_000)),
            "end": str(int(end.timestamp() * 1_000_000_000)),
            "limit": str(limit),
            "direction": "backward",
        }
    )
    request = urllib.request.Request(
        f"{query_url}?{params}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 300:
                raise RuntimeError(f"Loki query failed with HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Loki query failed: {exc}") from exc

    result = payload.get("data", {}).get("result", [])
    events: list[dict[str, Any]] = []
    for stream in result:
        for item in stream.get("values", []):
            if not isinstance(item, list) or len(item) != 2:
                continue
            line = item[1]
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def load_mutation_audit_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RuntimeError(f"mutation audit file not found: {path}")
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def collect_mutation_audit_entries(
    *,
    service_catalog: dict[str, Any] | None = None,
    lookback_days: int = DEFAULT_AUDIT_LOOKBACK_DAYS,
    mutation_audit_file: Path | None = None,
    loki_query_url: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    matchers = build_service_matchers(service_catalog)
    warnings: list[str] = []
    source_events: list[dict[str, Any]] = []

    audit_file = mutation_audit_file
    if audit_file is None:
        env_file = os.environ.get(MUTATION_AUDIT_QUERY_FILE_ENV)
        if env_file:
            audit_file = Path(env_file).expanduser()

    try:
        if audit_file is not None:
            source_events = load_mutation_audit_file(audit_file)
        else:
            source_events = query_loki_mutation_audit(lookback_days=lookback_days, loki_query_url=loki_query_url)
    except RuntimeError as exc:
        warnings.append(
            f"Mutation audit events are unavailable; the portal is showing receipts-only history ({exc})."
        )
        return [], warnings

    entries = []
    for event in source_events:
        try:
            timestamp = parse_timestamp(str(event.get("ts")), default_to_start_of_day=False)
        except ValueError:
            continue
        actor = ""
        if isinstance(event.get("actor"), dict):
            actor = str(event["actor"].get("id", ""))
        actor = actor or "unknown"
        action = str(event.get("action", "")).strip() or "mutation"
        target = str(event.get("target", "")).strip() or "unknown target"
        surface = str(event.get("surface", "")).strip() or "manual"
        change_type = "manual" if surface == "manual" else "command-catalog" if surface == "command-catalog" else surface
        text_parts = [action, target, str(event.get("evidence_ref", ""))]
        service_ids = infer_service_ids(text_parts, matchers)
        entries.append(
            {
                "id": str(event.get("correlation_id", f"{surface}:{target}")),
                "change_type": change_type,
                "timestamp": timestamp_to_iso(timestamp),
                "timestamp_precision": "datetime",
                "date_label": timestamp.strftime("%Y-%m-%d %H:%M UTC"),
                "actor": actor,
                "actor_class": str(event.get("actor", {}).get("class", actor_class_for_identity(actor))),
                "environment": "production",
                "outcome": str(event.get("outcome", "success")),
                "service_ids": service_ids,
                "service_names": render_services(service_ids, matchers),
                "vm_names": [],
                "targets": [target],
                "summary": f"{surface} {action} on {target}",
                "link_path": str(event.get("evidence_ref", "")),
                "source": "mutation_audit",
                "workflow_id": None,
                "adr": "0066",
                "metadata": {
                    "surface": surface,
                    "action": action,
                    "target": target,
                    "evidence_ref": event.get("evidence_ref"),
                    "params": event.get("params"),
                    "env_vars": event.get("env_vars"),
                    "error_detail": event.get("error_detail"),
                    "stack_trace": event.get("stack_trace"),
                    "job_payload": event.get("job_payload"),
                },
            }
        )
    return entries, warnings


def sort_history_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=lambda item: (item["timestamp"], item["id"]), reverse=True)


def filter_history_entries(
    entries: list[dict[str, Any]],
    *,
    service_id: str | None = None,
    environment: str | None = None,
    days: int | None = None,
) -> list[dict[str, Any]]:
    filtered = entries
    if service_id:
        filtered = [item for item in filtered if service_id in item.get("service_ids", [])]
    if environment:
        filtered = [item for item in filtered if item.get("environment") == environment]
    if days is not None:
        cutoff = utc_now() - dt.timedelta(days=days)
        filtered = [
            item
            for item in filtered
            if parse_timestamp(item["timestamp"], default_to_start_of_day=False) >= cutoff
        ]
    return filtered


def strip_none_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_none_values(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [strip_none_values(item) for item in value]
    return value


def load_deployment_history(
    *,
    receipts_dir: Path = LIVE_APPLY_DIR,
    promotions_dir: Path = PROMOTIONS_DIR,
    service_catalog: dict[str, Any] | None = None,
    mutation_audit_file: Path | None = None,
    loki_query_url: str | None = None,
    audit_lookback_days: int = DEFAULT_AUDIT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    if service_catalog is None:
        service_catalog = load_service_catalog_data()

    live_entries = collect_live_apply_entries(receipts_dir=receipts_dir, service_catalog=service_catalog)
    promotion_entries = collect_promotion_entries(
        promotions_dir=promotions_dir,
        receipts_dir=receipts_dir,
        service_catalog=service_catalog,
    )
    audit_entries, warnings = collect_mutation_audit_entries(
        service_catalog=service_catalog,
        lookback_days=audit_lookback_days,
        mutation_audit_file=mutation_audit_file,
        loki_query_url=loki_query_url,
    )
    entries = sort_history_entries(live_entries + promotion_entries + audit_entries)
    redacted_entries = redact_history_entries(entries)
    return {
        "entries": redacted_entries,
        "warnings": warnings,
        "stats": {
            "live_apply_count": len(live_entries),
            "promotion_count": len(promotion_entries),
            "mutation_audit_count": len(audit_entries),
        },
    }


def query_deployment_history(
    *,
    service_id: str | None = None,
    environment: str | None = None,
    days: int = 30,
    receipts_dir: Path = LIVE_APPLY_DIR,
    promotions_dir: Path = PROMOTIONS_DIR,
    service_catalog: dict[str, Any] | None = None,
    mutation_audit_file: Path | None = None,
    loki_query_url: str | None = None,
) -> dict[str, Any]:
    history = load_deployment_history(
        receipts_dir=receipts_dir,
        promotions_dir=promotions_dir,
        service_catalog=service_catalog,
        mutation_audit_file=mutation_audit_file,
        loki_query_url=loki_query_url,
        audit_lookback_days=max(days, DEFAULT_AUDIT_LOOKBACK_DAYS if days <= 0 else days),
    )
    entries = filter_history_entries(
        history["entries"],
        service_id=service_id,
        environment=environment,
        days=days if days > 0 else None,
    )
    return {
        "service_id": service_id or "all",
        "environment": environment or "all",
        "days": days,
        "count": len(entries),
        "warnings": history["warnings"],
        "entries": [strip_none_values(entry) for entry in entries],
    }
