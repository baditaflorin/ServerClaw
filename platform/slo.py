from __future__ import annotations

import json
import math
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from platform.repo import PYYAML_INSTALL_HINT, load_json, load_yaml


GRAFANA_DASHBOARD_UID = "lv3-slo-overview"
SLO_STATUS_BUDGET_WARN = 0.50
SLO_STATUS_BUDGET_CRITICAL = 0.10
K6_WARNING_THRESHOLD_PCT = 20.0
SLO_INDICATORS = {"availability", "latency"}
SLO_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _repo_path(repo_root: Path | None, *parts: str) -> Path:
    base = Path(__file__).resolve().parents[1] if repo_root is None else Path(repo_root)
    return base.joinpath(*parts)


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


def require_int(value: Any, path: str, minimum: int = 0) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def require_number(value: Any, path: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be numeric")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{path} must be <= {maximum}")
    return number


def metric_slug(slo_id: str) -> str:
    return slo_id.replace("-", "_")


def objective_ratio(slo: dict[str, Any]) -> float:
    return float(slo["objective_percent"]) / 100.0


def error_budget_ratio(slo: dict[str, Any]) -> float:
    return 1.0 - objective_ratio(slo)


def validate_slo_catalog(
    payload: dict[str, Any],
    *,
    service_catalog: dict[str, Any] | None = None,
    catalog_path: Path,
) -> dict[str, Any]:
    payload = require_mapping(payload, str(catalog_path))
    require_str(payload.get("schema_version"), "config/slo-catalog.json.schema_version")
    require_str(payload.get("review_note"), "config/slo-catalog.json.review_note")
    slos = require_list(payload.get("slos"), "config/slo-catalog.json.slos")
    if not slos:
        raise ValueError("config/slo-catalog.json.slos must not be empty")

    known_services = set()
    if service_catalog is not None:
        catalog = require_mapping(service_catalog, "config/service-capability-catalog.json")
        known_services = {
            require_str(service.get("id"), f"config/service-capability-catalog.json.services[{index}].id")
            for index, service in enumerate(require_list(catalog.get("services"), "config/service-capability-catalog.json.services"))
            if isinstance(service, dict)
        }

    seen_ids: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for index, raw_slo in enumerate(slos):
        path = f"config/slo-catalog.json.slos[{index}]"
        slo = require_mapping(raw_slo, path)
        slo_id = require_str(slo.get("id"), f"{path}.id")
        if not SLO_ID_PATTERN.fullmatch(slo_id):
            raise ValueError(f"{path}.id must be lower-kebab-case")
        if slo_id in seen_ids:
            raise ValueError(f"duplicate SLO id: {slo_id}")
        seen_ids.add(slo_id)

        service_id = require_str(slo.get("service_id"), f"{path}.service_id")
        if known_services and service_id not in known_services:
            raise ValueError(f"{path}.service_id references unknown service '{service_id}'")

        indicator = require_str(slo.get("indicator"), f"{path}.indicator")
        if indicator not in SLO_INDICATORS:
            raise ValueError(f"{path}.indicator must be one of {sorted(SLO_INDICATORS)}")

        pair = (service_id, indicator)
        if pair in seen_pairs:
            raise ValueError(f"duplicate SLO indicator for service '{service_id}': {indicator}")
        seen_pairs.add(pair)

        require_number(slo.get("objective_percent"), f"{path}.objective_percent", minimum=0.01, maximum=99.999)
        require_int(slo.get("window_days"), f"{path}.window_days", 1)
        target_url = require_str(slo.get("target_url"), f"{path}.target_url")
        if not (target_url.startswith("http://") or target_url.startswith("https://")):
            raise ValueError(f"{path}.target_url must start with http:// or https://")
        require_str(slo.get("probe_module"), f"{path}.probe_module")
        require_str(slo.get("description"), f"{path}.description")
        if indicator == "latency":
            require_number(slo.get("latency_threshold_ms"), f"{path}.latency_threshold_ms", minimum=1)
        elif "latency_threshold_ms" in slo:
            raise ValueError(f"{path}.latency_threshold_ms is only valid for latency SLOs")
    return payload


def load_slo_catalog(
    *,
    repo_root: Path | None = None,
    catalog_path: Path | None = None,
    service_catalog_path: Path | None = None,
) -> dict[str, Any]:
    resolved_catalog_path = catalog_path or _repo_path(repo_root, "config", "slo-catalog.json")
    resolved_service_catalog_path = service_catalog_path or _repo_path(repo_root, "config", "service-capability-catalog.json")
    service_catalog = load_json(resolved_service_catalog_path)
    return validate_slo_catalog(load_json(resolved_catalog_path), service_catalog=service_catalog, catalog_path=resolved_catalog_path)


def default_prometheus_url(*, repo_root: Path | None = None, stack_path: Path | None = None) -> str | None:
    env_url = os.environ.get("LV3_PROMETHEUS_URL")
    if env_url:
        return env_url.rstrip("/")
    resolved_stack_path = stack_path or _repo_path(repo_root, "versions", "stack.yaml")
    try:
        stack = require_mapping(load_yaml(resolved_stack_path), str(resolved_stack_path))
    except RuntimeError as exc:
        if PYYAML_INSTALL_HINT in str(exc):
            return None
        raise
    observed_state = require_mapping(stack.get("observed_state"), f"{resolved_stack_path}.observed_state")
    monitoring = require_mapping(observed_state.get("monitoring"), f"{resolved_stack_path}.observed_state.monitoring")
    url = monitoring.get("prometheus_internal_url")
    if isinstance(url, str) and url.strip():
        return url.rstrip("/")
    return None


def default_grafana_url(*, repo_root: Path | None = None, service_catalog_path: Path | None = None) -> str:
    env_url = os.environ.get("LV3_GRAFANA_URL")
    if env_url:
        return env_url.rstrip("/")
    resolved_service_catalog_path = service_catalog_path or _repo_path(repo_root, "config", "service-capability-catalog.json")
    service_catalog = require_mapping(load_json(resolved_service_catalog_path), str(resolved_service_catalog_path))
    for service in require_list(service_catalog.get("services"), f"{resolved_service_catalog_path}.services"):
        if isinstance(service, dict) and service.get("id") == "grafana":
            public_url = service.get("public_url")
            if isinstance(public_url, str) and public_url.strip():
                return public_url.rstrip("/")
    return "https://grafana.lv3.org"


def slo_metric_queries(slo: dict[str, Any]) -> dict[str, str]:
    slug = metric_slug(slo["id"])
    budget = error_budget_ratio(slo)
    window_days = int(slo["window_days"])
    return {
        "success_30d": f"slo:{slug}:success_ratio_{window_days}d",
        "budget_remaining": f"slo:{slug}:budget_remaining",
        "burn_rate_1h": f"slo:{slug}:burn_rate_1h",
        "time_to_budget_exhaustion_days": f"slo:{slug}:time_to_budget_exhaustion_days",
        "budget_ratio": f"{budget:.6f}",
    }


def format_budget_status(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "unknown"
    if value < SLO_STATUS_BUDGET_CRITICAL:
        return "critical"
    if value < SLO_STATUS_BUDGET_WARN:
        return "warning"
    return "healthy"


def prometheus_query_value(prometheus_url: str, expr: str, *, timeout: float = 5.0) -> float | None:
    query = urllib.parse.urlencode({"query": expr})
    request = urllib.request.Request(f"{prometheus_url}/api/v1/query?{query}", method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise ValueError(f"Prometheus query failed for expression: {expr}")
    data = require_mapping(payload.get("data"), "prometheus response.data")
    result = require_list(data.get("result"), "prometheus response.data.result")
    if not result:
        return None
    first = require_mapping(result[0], "prometheus response.data.result[0]")
    value = require_list(first.get("value"), "prometheus response.data.result[0].value")
    if len(value) != 2:
        raise ValueError("Prometheus response.data.result[0].value must contain timestamp and value")
    return float(value[1])


def relative_repo_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def receipt_recorded_at(receipt: dict[str, Any]) -> str:
    value = receipt.get("recorded_at")
    if isinstance(value, str) and value.strip():
        return value
    recorded_on = receipt.get("recorded_on")
    if isinstance(recorded_on, str) and recorded_on.strip():
        return f"{recorded_on}T00:00:00Z"
    return ""


def summarize_k6_receipt(receipt: dict[str, Any], path: Path, *, repo_root: Path) -> dict[str, Any] | None:
    service_id = receipt.get("service_id")
    scenario = receipt.get("scenario")
    if not isinstance(service_id, str) or not service_id.strip():
        return None
    if not isinstance(scenario, str) or not scenario.strip():
        return None
    metrics = receipt.get("metrics") if isinstance(receipt.get("metrics"), dict) else {}
    slo_assessment = receipt.get("slo_assessment") if isinstance(receipt.get("slo_assessment"), dict) else {}
    regression = receipt.get("regression") if isinstance(receipt.get("regression"), dict) else {}
    return {
        "service_id": service_id,
        "scenario": scenario,
        "receipt_path": relative_repo_path(path, repo_root),
        "recorded_at": receipt_recorded_at(receipt),
        "recorded_on": receipt.get("recorded_on"),
        "result": receipt.get("result"),
        "request_count": metrics.get("request_count"),
        "error_rate": metrics.get("error_rate"),
        "http_req_duration_p95_ms": metrics.get("http_req_duration_p95_ms"),
        "http_req_duration_avg_ms": metrics.get("http_req_duration_avg_ms"),
        "error_budget_remaining_pct": slo_assessment.get("error_budget_remaining_pct"),
        "error_budget_consumed_pct": slo_assessment.get("error_budget_consumed_pct"),
        "latency_threshold_passed": slo_assessment.get("latency_threshold_passed"),
        "regression_checked": regression.get("checked"),
        "regressed": regression.get("regressed"),
        "regression_ratio": regression.get("regression_ratio"),
    }


def load_latest_k6_receipts(*, repo_root: Path, receipts_dir: Path | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    target_dir = receipts_dir or _repo_path(repo_root, "receipts", "k6")
    if not target_dir.exists():
        return {}
    latest: dict[str, dict[str, dict[str, Any]]] = {}
    for path in sorted(target_dir.glob("*.json")):
        try:
            receipt = load_json(path)
        except Exception:  # noqa: BLE001
            continue
        summary = summarize_k6_receipt(receipt, path, repo_root=repo_root)
        if summary is None:
            continue
        by_service = latest.setdefault(summary["service_id"], {})
        existing = by_service.get(summary["scenario"])
        if existing is None or summary["recorded_at"] > existing["recorded_at"]:
            by_service[summary["scenario"]] = summary
    return latest


def current_k6_signal(latest_receipts: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for scenario in ("load", "soak", "smoke"):
        signal = latest_receipts.get(scenario)
        if signal is not None:
            return signal
    return None


def build_slo_status_entries(
    *,
    repo_root: Path | None = None,
    prometheus_url: str | None = None,
    query_fn: Callable[[str], float | None] | None = None,
    grafana_url: str | None = None,
    catalog_path: Path | None = None,
    service_catalog_path: Path | None = None,
    stack_path: Path | None = None,
) -> list[dict[str, Any]]:
    resolved_catalog_path = catalog_path or _repo_path(repo_root, "config", "slo-catalog.json")
    resolved_service_catalog_path = service_catalog_path or _repo_path(repo_root, "config", "service-capability-catalog.json")
    resolved_stack_path = stack_path or _repo_path(repo_root, "versions", "stack.yaml")
    catalog = load_slo_catalog(
        repo_root=repo_root,
        catalog_path=resolved_catalog_path,
        service_catalog_path=resolved_service_catalog_path,
    )
    effective_grafana_url = (grafana_url or default_grafana_url(repo_root=repo_root, service_catalog_path=resolved_service_catalog_path)).rstrip("/")
    effective_prometheus_url = default_prometheus_url(repo_root=repo_root, stack_path=resolved_stack_path) if prometheus_url is None else prometheus_url
    resolved_repo_root = Path(repo_root) if repo_root is not None else resolved_catalog_path.parents[1]
    latest_k6_receipts = load_latest_k6_receipts(repo_root=resolved_repo_root, receipts_dir=_repo_path(resolved_repo_root, "receipts", "k6"))
    effective_query = query_fn
    if effective_query is None and effective_prometheus_url:
        effective_query = lambda expr: prometheus_query_value(effective_prometheus_url, expr)

    entries: list[dict[str, Any]] = []
    for slo in catalog["slos"]:
        queries = slo_metric_queries(slo)
        live_metrics: dict[str, float | None] = {
            "success_ratio_30d": None,
            "budget_remaining": None,
            "burn_rate_1h": None,
            "time_to_budget_exhaustion_days": None,
        }
        metrics_error: str | None = None
        if effective_query is not None:
            try:
                live_metrics["success_ratio_30d"] = effective_query(queries["success_30d"])
                live_metrics["budget_remaining"] = effective_query(queries["budget_remaining"])
                live_metrics["burn_rate_1h"] = effective_query(queries["burn_rate_1h"])
                live_metrics["time_to_budget_exhaustion_days"] = effective_query(queries["time_to_budget_exhaustion_days"])
            except Exception as exc:  # noqa: BLE001
                metrics_error = str(exc)
        entries.append(
            {
                "id": slo["id"],
                "service_id": slo["service_id"],
                "indicator": slo["indicator"],
                "objective_percent": slo["objective_percent"],
                "window_days": slo["window_days"],
                "target_url": slo["target_url"],
                "description": slo["description"],
                "latency_threshold_ms": slo.get("latency_threshold_ms"),
                "queries": {
                    "success_ratio_30d": queries["success_30d"],
                    "budget_remaining": queries["budget_remaining"],
                    "burn_rate_1h": queries["burn_rate_1h"],
                    "time_to_budget_exhaustion_days": queries["time_to_budget_exhaustion_days"],
                },
                "metrics": live_metrics,
                "metrics_available": metrics_error is None and any(value is not None for value in live_metrics.values()),
                "metrics_error": metrics_error,
                "status": format_budget_status(live_metrics["budget_remaining"]),
                "k6": {
                    "current_signal": current_k6_signal(latest_k6_receipts.get(slo["service_id"], {})),
                    "latest_receipts": latest_k6_receipts.get(slo["service_id"], {}),
                    "warning_threshold_percent": K6_WARNING_THRESHOLD_PCT,
                },
                "dashboard_url": (
                    f"{effective_grafana_url}/d/{GRAFANA_DASHBOARD_UID}/{GRAFANA_DASHBOARD_UID}"
                    f"?var-slo={urllib.parse.quote(slo['id'])}"
                ),
            }
        )
    return entries


def find_budget_breaches(
    entries: list[dict[str, Any]],
    *,
    threshold: float = SLO_STATUS_BUDGET_CRITICAL,
) -> list[dict[str, Any]]:
    breaches = []
    for entry in entries:
        budget = entry["metrics"].get("budget_remaining")
        if budget is None:
            continue
        if budget < threshold:
            breaches.append(entry)
    return breaches
