#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path, write_json
from maintenance_window_tool import list_active_windows_best_effort
from mutation_audit import build_event, emit_event_best_effort, resolve_local_sink_path
from platform.web import WebSearchClient


RULES_PATH = repo_path("config", "triage-rules.yaml")
AUTO_CHECK_ALLOWLIST_PATH = repo_path("config", "triage-auto-check-allowlist.yaml")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
CERTIFICATE_CATALOG_PATH = repo_path("config", "certificate-catalog.json")
DEPENDENCY_GRAPH_PATH = repo_path("config", "dependency-graph.json")
LIVE_APPLY_RECEIPTS_DIR = repo_path("receipts", "live-applies")
DEFAULT_REPORT_DIR = repo_path(".local", "triage", "reports")
DEFAULT_CALIBRATION_PATH = repo_path(".local", "triage", "calibration", "latest.json")
TRIAGE_LOKI_QUERY_URL_ENV = "LV3_TRIAGE_LOKI_QUERY_URL"
TRIAGE_MATTERMOST_WEBHOOK_ENV = "LV3_TRIAGE_MATTERMOST_WEBHOOK_URL"
DEFAULT_LOG_LOOKBACK_MINUTES = 15
DEFAULT_DEPLOYMENT_LOOKBACK_HOURS = 2
DEFAULT_MUTATION_LOOKBACK_HOURS = 2
ERROR_WORDS = ("error", "exception", "traceback", "fatal", "critical")
SEVERITY_WORDS = {
    "debug": 10,
    "info": 20,
    "notice": 25,
    "warning": 30,
    "warn": 30,
    "error": 40,
    "critical": 50,
    "fatal": 60,
}
TEMPLATE_PATTERN = re.compile(r"{{\s*([^}]+?)\s*}}")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = dt.datetime.combine(dt.date.fromisoformat(value), dt.time(0, tzinfo=dt.timezone.utc))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def bool_from_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "firing", "critical", "down", "failed"}
    return bool(value)


def normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def load_service_catalog() -> list[dict[str, Any]]:
    payload = load_json(SERVICE_CATALOG_PATH, default={"services": []})
    services = payload.get("services", [])
    if not isinstance(services, list):
        raise ValueError("config/service-capability-catalog.json must define a services list")
    return services


def service_identifier_candidates(service: dict[str, Any]) -> list[str]:
    values = [
        service.get("id", ""),
        service.get("name", ""),
        service.get("vm", ""),
        service.get("public_url", ""),
        service.get("internal_url", ""),
        service.get("subdomain", ""),
    ]
    return [normalize_text(str(item)) for item in values if isinstance(item, str) and item.strip()]


def service_matches_payload(service: dict[str, Any], payload: dict[str, Any]) -> bool:
    tokens = service_identifier_candidates(service)
    haystack = normalize_text(json.dumps(payload, sort_keys=True))
    return any(token and token in haystack for token in tokens)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(repo_path()))
    except ValueError:
        return str(path)


def load_certificate_catalog() -> list[dict[str, Any]]:
    payload = load_json(CERTIFICATE_CATALOG_PATH, default={"certificates": []})
    certificates = payload.get("certificates", [])
    if not isinstance(certificates, list):
        raise ValueError("config/certificate-catalog.json must define a certificates list")
    return certificates


def load_dependency_graph() -> dict[str, Any]:
    return load_json(DEPENDENCY_GRAPH_PATH, default={"nodes": [], "edges": []})


def load_triage_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a mapping")
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError(f"{path}.schema_version must be a non-empty string")
    rule_table_version = payload.get("rule_table_version")
    if not isinstance(rule_table_version, str) or not rule_table_version.strip():
        raise ValueError(f"{path}.rule_table_version must be a non-empty string")
    rules = payload.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"{path}.rules must be a non-empty list")
    for index, rule in enumerate(rules):
        validate_rule(rule, f"{path}.rules[{index}]")
    return payload


def validate_rule(rule: dict[str, Any], path: str) -> None:
    if not isinstance(rule, dict):
        raise ValueError(f"{path} must be a mapping")
    for field in ("id", "description", "hypothesis", "cheapest_first_action"):
        value = rule.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}.{field} must be a non-empty string")
    confidence = rule.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        raise ValueError(f"{path}.confidence must be numeric between 0 and 1")
    auto_check = rule.get("auto_check")
    if not isinstance(auto_check, bool):
        raise ValueError(f"{path}.auto_check must be boolean")
    conditions = rule.get("conditions")
    if not isinstance(conditions, dict) or not conditions:
        raise ValueError(f"{path}.conditions must be a non-empty mapping")
    validate_condition_group(conditions, f"{path}.conditions")
    checks = rule.get("discriminating_checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"{path}.discriminating_checks must be a non-empty list")
    for check_index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ValueError(f"{path}.discriminating_checks[{check_index}] must be a mapping")
        check_type = check.get("type")
        if not isinstance(check_type, str) or not check_type.strip():
            raise ValueError(f"{path}.discriminating_checks[{check_index}].type must be a non-empty string")


def validate_condition_group(group: dict[str, Any], path: str) -> None:
    if "signal" in group:
        signal = group.get("signal")
        if not isinstance(signal, str) or not signal.strip():
            raise ValueError(f"{path}.signal must be a non-empty string")
        allowed_fields = {"signal", "value", "eq", "neq", "gt", "gte", "lt", "lte", "contains", "in", "exists"}
        unexpected = sorted(set(group) - allowed_fields)
        if unexpected:
            raise ValueError(f"{path} contains unsupported fields: {', '.join(unexpected)}")
        return

    keys = [key for key in ("all", "any", "not") if key in group]
    if len(keys) != 1:
        raise ValueError(f"{path} must define exactly one of all, any, or not")
    entries = group[keys[0]]
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path}.{keys[0]} must be a non-empty list")
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ValueError(f"{path}.{keys[0]}[{index}] must be a mapping")
        validate_condition_group(item, f"{path}.{keys[0]}[{index}]")


def load_auto_check_allowlist(path: Path = AUTO_CHECK_ALLOWLIST_PATH) -> set[str]:
    payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a mapping")
    entries = payload.get("allowed_check_types")
    if not isinstance(entries, list):
        raise ValueError(f"{path}.allowed_check_types must be a list")
    result: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path}.allowed_check_types[{index}] must be a non-empty string")
        result.add(item)
    return result


def infer_service_id(alert_payload: dict[str, Any], services: list[dict[str, Any]]) -> str:
    for field in ("service_id", "affected_service"):
        value = alert_payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    labels = alert_payload.get("labels")
    if isinstance(labels, dict):
        for field in ("service", "service_id", "affected_service"):
            value = labels.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for service in services:
        if service_matches_payload(service, alert_payload):
            return service["id"]
    raise ValueError("could not infer affected service from alert payload")


def alert_name(alert_payload: dict[str, Any]) -> str:
    for field in ("alert_name", "triggered_by_alert", "name"):
        value = alert_payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    labels = alert_payload.get("labels")
    if isinstance(labels, dict):
        for field in ("alertname", "name"):
            value = labels.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "unknown_alert"


def incident_id(alert_payload: dict[str, Any], service_id: str) -> str:
    for field in ("incident_id", "fingerprint"):
        value = alert_payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    starts_at = parse_timestamp(alert_payload.get("starts_at")) or utc_now()
    return f"inc-{starts_at.strftime('%Y%m%dT%H%M%SZ')}-{service_id}-{uuid.uuid4().hex[:6]}"


def resolve_status(alert_payload: dict[str, Any]) -> str:
    for field in ("status",):
        value = alert_payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    labels = alert_payload.get("labels")
    if isinstance(labels, dict):
        value = labels.get("status")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return "firing"


def load_recent_deployments(service: dict[str, Any], *, lookback_hours: int = DEFAULT_DEPLOYMENT_LOOKBACK_HOURS) -> list[dict[str, Any]]:
    if not LIVE_APPLY_RECEIPTS_DIR.exists():
        return []
    cutoff = utc_now() - dt.timedelta(hours=lookback_hours)
    deployments: list[dict[str, Any]] = []
    for path in sorted(LIVE_APPLY_RECEIPTS_DIR.rglob("*.json")):
        try:
            payload = load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        applied_at = parse_timestamp(payload.get("recorded_on") or payload.get("applied_on"))
        if applied_at is None or applied_at < cutoff:
            continue
        if not service_matches_payload(service, payload):
            continue
        deployments.append(
            {
                "receipt_id": payload.get("receipt_id"),
                "workflow_id": payload.get("workflow_id"),
                "actor": payload.get("recorded_by", "unknown"),
                "summary": payload.get("summary", ""),
                "ts": isoformat(applied_at),
                "path": display_path(path),
            }
        )
    return deployments


def load_recent_mutation_events(service: dict[str, Any], *, lookback_hours: int = DEFAULT_MUTATION_LOOKBACK_HOURS) -> list[dict[str, Any]]:
    sink_path = resolve_local_sink_path(None)
    if sink_path is None or not sink_path.exists():
        return []
    cutoff = utc_now() - dt.timedelta(hours=lookback_hours)
    events: list[dict[str, Any]] = []
    for raw_line in sink_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        ts = parse_timestamp(event.get("ts"))
        if ts is None or ts < cutoff:
            continue
        if not service_matches_payload(service, event):
            continue
        events.append(event)
    return events


def resolve_triage_loki_query_url(loki_query_url: str | None = None) -> str | None:
    candidate = loki_query_url or os.environ.get(TRIAGE_LOKI_QUERY_URL_ENV) or os.environ.get("LV3_LOKI_URL")
    if not candidate:
        return None
    candidate = candidate.strip()
    if not candidate or candidate.lower() == "off":
        return None
    if candidate.endswith("/push"):
        return candidate[:-5] + "/query_range"
    return candidate


def query_recent_logs(
    service_id: str,
    *,
    lookback_minutes: int = DEFAULT_LOG_LOOKBACK_MINUTES,
    loki_query_url: str | None = None,
) -> list[dict[str, Any]]:
    query_url = resolve_triage_loki_query_url(loki_query_url)
    if not query_url:
        return []
    end = utc_now()
    start = end - dt.timedelta(minutes=lookback_minutes)
    params = urllib.parse.urlencode(
        {
            "query": f'{{service="{service_id}"}}',
            "start": str(int(start.timestamp() * 1_000_000_000)),
            "end": str(int(end.timestamp() * 1_000_000_000)),
            "limit": "200",
            "direction": "backward",
        }
    )
    request = urllib.request.Request(
        f"{query_url}?{params}",
        headers={"Accept": "application/json", "User-Agent": "incident-triage/0.1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 300:
                raise RuntimeError(f"Loki query failed with HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, RuntimeError):
        return []
    entries: list[dict[str, Any]] = []
    for stream in payload.get("data", {}).get("result", []):
        labels = stream.get("stream", {})
        for item in stream.get("values", []):
            if not isinstance(item, list) or len(item) != 2:
                continue
            entries.append({"ts_ns": item[0], "line": item[1], "labels": labels})
    return entries


def log_line_is_error(entry: dict[str, Any]) -> bool:
    labels = entry.get("labels", {})
    if isinstance(labels, dict):
        level = labels.get("level")
        if isinstance(level, str) and SEVERITY_WORDS.get(level.lower(), 0) >= SEVERITY_WORDS["error"]:
            return True
    line = str(entry.get("line", "")).lower()
    return any(word in line for word in ERROR_WORDS)


def extract_metrics(alert_payload: dict[str, Any]) -> dict[str, float]:
    metrics = alert_payload.get("metrics", {})
    if not isinstance(metrics, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            result[key] = float(value)
            continue
        if isinstance(value, str):
            try:
                result[key] = float(value)
            except ValueError:
                continue
    return result


def collect_certificate_observation(
    service_id: str,
    alert_payload: dict[str, Any],
    certificates: list[dict[str, Any]],
) -> dict[str, Any]:
    explicit = alert_payload.get("certificate")
    if isinstance(explicit, dict):
        return explicit
    for certificate in certificates:
        if certificate.get("service_id") == service_id:
            return certificate
    return {}


def expiry_days_from_certificate(observation: dict[str, Any]) -> int | None:
    for key in ("expiry_days", "days_until_expiry", "tls_cert_expiry_days"):
        value = observation.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    material = observation.get("material")
    if isinstance(material, dict):
        not_after = material.get("not_after")
        parsed = parse_timestamp(not_after if isinstance(not_after, str) else None)
        if parsed is not None:
            delta = parsed - utc_now()
            return int(delta.total_seconds() // 86400)
    return None


def derive_dependencies(
    service_id: str,
    alert_payload: dict[str, Any],
    dependency_graph: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    explicit = alert_payload.get("dependencies")
    if isinstance(explicit, dict):
        upstream = explicit.get("upstream", [])
        downstream = explicit.get("downstream", [])
        return {
            "upstream": upstream if isinstance(upstream, list) else [],
            "downstream": downstream if isinstance(downstream, list) else [],
        }

    upstream: list[dict[str, Any]] = []
    downstream: list[dict[str, Any]] = []
    edges = dependency_graph.get("edges", [])
    if not isinstance(edges, list):
        return {"upstream": [], "downstream": []}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("from")
        target = edge.get("to")
        if source == service_id:
            downstream.append({"service_id": target, "healthy": None, "relationship": edge.get("kind", "depends_on")})
        if target == service_id:
            upstream.append({"service_id": source, "healthy": None, "relationship": edge.get("kind", "depends_on")})
    return {"upstream": upstream, "downstream": downstream}


def maintenance_window_active(service_id: str) -> bool:
    active_windows = list_active_windows_best_effort(stderr=io.StringIO())
    return f"maintenance/{service_id}" in active_windows or "maintenance/all" in active_windows


def detect_service_health_failure(alert_payload: dict[str, Any]) -> bool:
    status = resolve_status(alert_payload)
    if status in {"firing", "critical", "down", "failed"}:
        return True
    name = alert_name(alert_payload).lower()
    if any(fragment in name for fragment in ("health", "probe", "availability", "down")):
        return True
    return bool_from_value(alert_payload.get("service_health_probe_failing"))


def extract_signals(context: dict[str, Any]) -> dict[str, Any]:
    alert_payload = context["alert_payload"]
    metrics = context["metrics"]
    dependencies = context["dependencies"]
    logs = context["logs"]
    recent_deployments = context["recent_deployments"]
    mutation_events = context["recent_mutations"]
    certificate = context["certificate"]

    unhealthy_upstreams = [
        item for item in dependencies["upstream"] if bool_from_value(item.get("healthy")) is False
    ]
    degraded_downstreams = [
        item for item in dependencies["downstream"] if bool_from_value(item.get("affected")) or bool_from_value(item.get("healthy")) is False
    ]
    deployment_actor = recent_deployments[0]["actor"] if recent_deployments else "unknown"

    recent_drift_detected = bool_from_value(alert_payload.get("recent_drift_detected"))
    if not recent_drift_detected:
        recent_drift_detected = any("drift" in str(event.get("action", "")).lower() for event in mutation_events)

    db_healthy = None
    for item in dependencies["upstream"]:
        service_id = str(item.get("service_id", "")).lower()
        if "postgres" in service_id or service_id.endswith("db") or item.get("relationship") == "database":
            db_healthy = bool_from_value(item.get("healthy"))
            break

    signals: dict[str, Any] = {
        "service_health_probe_failing": detect_service_health_failure(alert_payload),
        "recent_deployment_within_2h": bool(recent_deployments),
        "deployment_actor": deployment_actor,
        "error_log_count_15m": sum(1 for entry in logs if log_line_is_error(entry)),
        "tls_cert_expiry_days": expiry_days_from_certificate(certificate),
        "downstream_services_affected_count": len(degraded_downstreams),
        "maintenance_window_active": context["maintenance_window_active"],
        "cpu_utilisation_pct": metrics.get("cpu_utilisation_pct"),
        "memory_utilisation_pct": metrics.get("memory_utilisation_pct"),
        "disk_utilisation_pct": metrics.get("disk_utilisation_pct"),
        "db_connection_count_pct": metrics.get("db_connection_count_pct"),
        "upstream_db_healthy": db_healthy,
        "unhealthy_upstream_count": len(unhealthy_upstreams),
        "recent_drift_detected": recent_drift_detected,
    }

    for key, value in alert_payload.get("signal_overrides", {}).items() if isinstance(alert_payload.get("signal_overrides"), dict) else []:
        signals[key] = value

    return signals


def compare_signal(actual: Any, clause: dict[str, Any]) -> tuple[bool, str | None]:
    signal_name = clause["signal"]
    if clause.get("exists") is True:
        matched = actual is not None
        return matched, f"{signal_name} exists" if matched else None
    if clause.get("exists") is False:
        matched = actual is None
        return matched, f"{signal_name} missing" if matched else None

    comparisons = (
        ("value", lambda a, b: a == b),
        ("eq", lambda a, b: a == b),
        ("neq", lambda a, b: a != b),
        ("gt", lambda a, b: a is not None and a > b),
        ("gte", lambda a, b: a is not None and a >= b),
        ("lt", lambda a, b: a is not None and a < b),
        ("lte", lambda a, b: a is not None and a <= b),
        ("contains", lambda a, b: isinstance(a, str) and str(b) in a),
        ("in", lambda a, b: a in b if isinstance(b, list) else False),
    )
    for key, predicate in comparisons:
        if key not in clause:
            continue
        expected = clause[key]
        matched = predicate(actual, expected)
        if matched:
            return True, f"{signal_name} {key} {expected!r} (actual={actual!r})"
        return False, None
    raise ValueError(f"condition for signal '{signal_name}' does not define a comparison")


def evaluate_condition_group(group: dict[str, Any], signals: dict[str, Any]) -> tuple[bool, list[str]]:
    if "signal" in group:
        matched, evidence = compare_signal(signals.get(group["signal"]), group)
        return matched, [evidence] if evidence else []

    if "all" in group:
        evidence: list[str] = []
        for item in group["all"]:
            matched, item_evidence = evaluate_condition_group(item, signals)
            if not matched:
                return False, []
            evidence.extend(item_evidence)
        return True, evidence

    if "any" in group:
        combined: list[str] = []
        for item in group["any"]:
            matched, item_evidence = evaluate_condition_group(item, signals)
            if matched:
                combined.extend(item_evidence)
        return bool(combined), combined

    if "not" in group:
        evidence: list[str] = []
        for item in group["not"]:
            matched, _item_evidence = evaluate_condition_group(item, signals)
            if matched:
                return False, []
            evidence.append("negated condition satisfied")
        return True, evidence

    raise ValueError("unsupported condition group")


def template_context(context: dict[str, Any], signals: dict[str, Any]) -> dict[str, Any]:
    service = context["service"]
    values = {
        "affected_service": context["service_id"],
        "service_name": service.get("name", context["service_id"]),
        "triggered_by_alert": context["alert_name"],
        "incident_id": context["incident_id"],
        "deployment_actor": signals.get("deployment_actor"),
        "db_name": context["service_id"],
    }
    values.update(signals)
    return values


def render_template_string(value: str, values: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        resolved = values.get(key)
        if resolved is None:
            return match.group(0)
        return str(resolved)

    return TEMPLATE_PATTERN.sub(replace, value)


def render_templates(value: Any, values: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_template_string(value, values)
    if isinstance(value, list):
        return [render_templates(item, values) for item in value]
    if isinstance(value, dict):
        return {key: render_templates(item, values) for key, item in value.items()}
    return value


def evaluate_rules(rule_payload: dict[str, Any], context: dict[str, Any], signals: dict[str, Any]) -> list[dict[str, Any]]:
    rendered_values = template_context(context, signals)
    hypotheses: list[dict[str, Any]] = []
    for rule in rule_payload["rules"]:
        matched, evidence = evaluate_condition_group(rule["conditions"], signals)
        if not matched:
            continue
        rendered_checks = render_templates(rule["discriminating_checks"], rendered_values)
        hypotheses.append(
            {
                "id": rule["id"],
                "hypothesis": render_template_string(rule["hypothesis"], rendered_values),
                "description": rule["description"],
                "confidence": float(rule["confidence"]),
                "evidence": evidence,
                "discriminating_checks": rendered_checks,
                "cheapest_first_action": render_template_string(rule["cheapest_first_action"], rendered_values),
                "auto_check": rule["auto_check"],
            }
        )

    if hypotheses:
        hypotheses.sort(key=lambda item: (-item["confidence"], item["id"]))
        for index, hypothesis in enumerate(hypotheses[:3], start=1):
            hypothesis["rank"] = index
        return hypotheses[:3]

    return [
        {
            "rank": 1,
            "id": "unclassified-incident",
            "hypothesis": "No triage rule matched. Inspect recent logs and upstream dependencies manually.",
            "description": "Fallback hypothesis when no configured rule matches the assembled signal set.",
            "confidence": 0.2,
            "evidence": [
                f"service_health_probe_failing={signals.get('service_health_probe_failing')}",
                f"error_log_count_15m={signals.get('error_log_count_15m')}",
            ],
            "discriminating_checks": [
                {"type": "log_query", "query": f'service="{context["service_id"]}" level="error"', "window": "15m"},
                {"type": "manual", "instruction": f"Check upstream dependencies for {context['service_id']}"},
            ],
            "cheapest_first_action": f"Inspect logs for {context['service_id']} and confirm upstream health.",
            "auto_check": False,
        }
    ]


def execute_auto_check(
    hypothesis: dict[str, Any] | None,
    *,
    allowlist: set[str],
    context: dict[str, Any],
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    if not hypothesis or not hypothesis.get("auto_check"):
        return None
    checks = hypothesis.get("discriminating_checks", [])
    if not checks:
        return {"status": "skipped", "reason": "no discriminating checks defined"}
    check = checks[0]
    check_type = check.get("type")
    if check_type not in allowlist:
        return {"status": "skipped", "reason": f"check type '{check_type}' is not allowlisted"}

    if check_type == "cert_check":
        return {
            "status": "executed",
            "type": check_type,
            "target": check.get("target", context["service_id"]),
            "observed": {"tls_cert_expiry_days": signals.get("tls_cert_expiry_days")},
        }
    if check_type == "log_query":
        query = str(check.get("query", "")).lower()
        matched_lines = [entry.get("line", "") for entry in context["logs"] if all(token in str(entry.get("line", "")).lower() for token in query.replace('"', "").split() if token)]
        return {
            "status": "executed",
            "type": check_type,
            "query": check.get("query"),
            "matched_line_count": len(matched_lines),
            "sample": matched_lines[:3],
        }
    if check_type == "metric_query":
        return {
            "status": "executed",
            "type": check_type,
            "query": check.get("query"),
            "observed_metrics": context["metrics"],
        }
    return {"status": "skipped", "reason": f"no local executor for '{check_type}'"}


def derive_web_search_query(context: dict[str, Any]) -> str | None:
    explicit = context["alert_payload"].get("error_message")
    if isinstance(explicit, str) and explicit.strip():
        snippet = " ".join(explicit.split())[:180]
        return f'site:github.com OR site:stackoverflow.com "{snippet}"'

    for entry in context["logs"]:
        if not log_line_is_error(entry):
            continue
        line = " ".join(str(entry.get("line", "")).split())
        if not line:
            continue
        return f'site:github.com OR site:stackoverflow.com "{line[:180]}"'

    if context["alert_name"] != "unknown_alert":
        return f'{context["service_id"]} {context["alert_name"]}'
    return None


def search_web_references(query: str, *, max_results: int = 3) -> list[dict[str, str]]:
    try:
        results = WebSearchClient().search(query, max_results=max_results)
    except Exception:
        return []
    return [
        {"title": result.title, "url": result.url, "content": result.content}
        for result in results
    ]


def build_context(alert_payload: dict[str, Any], *, loki_query_url: str | None = None) -> dict[str, Any]:
    services = load_service_catalog()
    service_id = infer_service_id(alert_payload, services)
    service = next(service for service in services if service["id"] == service_id)
    dependencies = derive_dependencies(service_id, alert_payload, load_dependency_graph())
    logs = alert_payload.get("logs")
    if not isinstance(logs, list):
        logs = query_recent_logs(service_id, loki_query_url=loki_query_url)
    return {
        "incident_id": incident_id(alert_payload, service_id),
        "service_id": service_id,
        "service": service,
        "alert_name": alert_name(alert_payload),
        "status": resolve_status(alert_payload),
        "alert_payload": alert_payload,
        "metrics": extract_metrics(alert_payload),
        "dependencies": dependencies,
        "recent_deployments": load_recent_deployments(service),
        "recent_mutations": load_recent_mutation_events(service),
        "logs": logs,
        "certificate": collect_certificate_observation(service_id, alert_payload, load_certificate_catalog()),
        "maintenance_window_active": maintenance_window_active(service_id),
    }


def report_path_for_incident(incident: str, *, report_dir: Path = DEFAULT_REPORT_DIR) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", incident).strip("-") or "incident"
    return report_dir / f"{safe}.json"


def build_report(
    alert_payload: dict[str, Any],
    *,
    rules_path: Path = RULES_PATH,
    auto_check_allowlist_path: Path = AUTO_CHECK_ALLOWLIST_PATH,
    loki_query_url: str | None = None,
) -> dict[str, Any]:
    started = utc_now()
    context = build_context(alert_payload, loki_query_url=loki_query_url)
    rules = load_triage_rules(rules_path)
    signals = extract_signals(context)
    hypotheses = evaluate_rules(rules, context, signals)
    auto_check = execute_auto_check(
        hypotheses[0] if hypotheses else None,
        allowlist=load_auto_check_allowlist(auto_check_allowlist_path),
        context=context,
        signals=signals,
    )
    elapsed_ms = int((utc_now() - started).total_seconds() * 1000)
    report = {
        "incident_id": context["incident_id"],
        "affected_service": context["service_id"],
        "triggered_by_alert": context["alert_name"],
        "triage_at": isoformat(utc_now()),
        "status": context["status"],
        "hypotheses": hypotheses,
        "signal_set": signals,
        "rule_table_version": rules["rule_table_version"],
        "elapsed_ms": elapsed_ms,
        "context_summary": {
            "recent_deployment_count": len(context["recent_deployments"]),
            "recent_mutation_count": len(context["recent_mutations"]),
            "recent_log_count": len(context["logs"]),
            "upstream_dependency_count": len(context["dependencies"]["upstream"]),
            "downstream_dependency_count": len(context["dependencies"]["downstream"]),
            "maintenance_window_active": context["maintenance_window_active"],
        },
        "auto_check_result": auto_check,
    }

    if hypotheses and hypotheses[0].get("id") == "unclassified-incident":
        web_search_query = derive_web_search_query(context)
        if web_search_query:
            web_search_references = search_web_references(web_search_query)
            if web_search_references:
                report["web_search_query"] = web_search_query
                report["web_search_references"] = web_search_references

    return report


def render_mattermost_summary(report: dict[str, Any]) -> str:
    lines = [
        f"ADR 0114 triage report for `{report['affected_service']}`",
        f"- incident: `{report['incident_id']}`",
        f"- alert: `{report['triggered_by_alert']}`",
        f"- elapsed: `{report['elapsed_ms']}ms`",
    ]
    for hypothesis in report["hypotheses"]:
        lines.append(
            f"- #{hypothesis['rank']} `{hypothesis['id']}` ({hypothesis['confidence']:.2f}): "
            f"{hypothesis['hypothesis']} | action: {hypothesis['cheapest_first_action']}"
        )
    return "\n".join(lines)


def post_json_webhook(url: str, payload: dict[str, Any]) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 300:
            raise RuntimeError(f"Webhook POST failed with HTTP {response.status}")


def emit_triage_report(
    report: dict[str, Any],
    *,
    emit_audit: bool,
    mattermost_webhook_url: str | None,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    path = report_path_for_incident(report["incident_id"], report_dir=report_dir)
    write_json(path, report, indent=2, sort_keys=True)
    emitted = {"report_path": str(path)}

    if emit_audit:
        event = build_event(
            actor_class="automation",
            actor_id="incident-triage-engine",
            surface="windmill",
            action="triage.report_created",
            target=report["affected_service"],
            outcome="success",
            correlation_id=report["incident_id"],
            evidence_ref=display_path(path),
        )
        emitted["mutation_audit_emitted"] = emit_event_best_effort(
            event,
            context="incident triage",
        )

    webhook = mattermost_webhook_url or os.environ.get(TRIAGE_MATTERMOST_WEBHOOK_ENV, "").strip()
    if webhook:
        post_json_webhook(webhook, {"text": render_mattermost_summary(report)})
        emitted["mattermost_posted"] = True
    else:
        emitted["mattermost_posted"] = False

    return emitted


def load_alert_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def parse_signal_overrides(pairs: list[str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"signal override '{pair}' must use key=value format")
        key, raw_value = pair.split("=", 1)
        lowered = raw_value.lower()
        if lowered in {"true", "false"}:
            value: Any = lowered == "true"
        else:
            try:
                value = int(raw_value)
            except ValueError:
                try:
                    value = float(raw_value)
                except ValueError:
                    value = raw_value
        overrides[key] = value
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0114 rule-based incident triage engine.")
    parser.add_argument("--payload", type=Path, help="Path to a JSON alert payload.")
    parser.add_argument("--service", help="Affected service id for ad hoc triage.")
    parser.add_argument("--alert-name", default="manual_triage", help="Alert name for ad hoc triage.")
    parser.add_argument("--status", default="firing", help="Alert status for ad hoc triage.")
    parser.add_argument("--signal", action="append", default=[], help="Signal override in key=value format.")
    parser.add_argument("--emit", action="store_true", help="Write the triage report, emit mutation audit, and post webhook summary.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Directory where report JSON files are written.")
    parser.add_argument("--mattermost-webhook-url", help="Optional Mattermost incoming webhook URL.")
    parser.add_argument("--loki-query-url", help="Optional Loki query_range URL override.")
    parser.add_argument("--rules-path", type=Path, default=RULES_PATH, help="Override the triage rule table path.")
    parser.add_argument(
        "--auto-check-allowlist-path",
        type=Path,
        default=AUTO_CHECK_ALLOWLIST_PATH,
        help="Override the auto-check allowlist path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.payload:
            alert_payload = load_alert_payload(args.payload)
        else:
            if not args.service:
                raise ValueError("--service is required when --payload is not provided")
            alert_payload = {
                "service_id": args.service,
                "alert_name": args.alert_name,
                "status": args.status,
            }
        signal_overrides = parse_signal_overrides(args.signal)
        if signal_overrides:
            alert_payload["signal_overrides"] = {
                **(alert_payload.get("signal_overrides", {}) if isinstance(alert_payload.get("signal_overrides"), dict) else {}),
                **signal_overrides,
            }
        report = build_report(
            alert_payload,
            rules_path=args.rules_path,
            auto_check_allowlist_path=args.auto_check_allowlist_path,
            loki_query_url=args.loki_query_url,
        )
        if args.emit:
            report["emission"] = emit_triage_report(
                report,
                emit_audit=True,
                mattermost_webhook_url=args.mattermost_webhook_url,
                report_dir=args.report_dir,
            )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Incident triage", exc)


if __name__ == "__main__":
    sys.exit(main())
