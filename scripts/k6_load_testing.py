#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json
from container_image_policy import load_image_catalog
from platform.events.publisher import publish_nats_events
from platform.slo import error_budget_ratio, load_slo_catalog


REPO_ROOT = Path(__file__).resolve().parents[1]
CAPACITY_MODEL_PATH = REPO_ROOT / "config" / "capacity-model.json"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
K6_SCRIPT_PATH = REPO_ROOT / "config" / "k6" / "scripts" / "http-slo-probe.js"
K6_RECEIPTS_DIR = REPO_ROOT / "receipts" / "k6"
K6_RAW_DIR = K6_RECEIPTS_DIR / "raw"
K6_RECEIPT_SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "k6-receipt.schema.json"
SUMMARY_KEY_PATTERN = re.compile(r"^(?P<metric>[a-z0-9_]+)\{service_id:(?P<service_id>[a-z0-9_]+)\}$")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
DEFAULT_MAX_ERROR_RATE = 0.01
DEFAULT_WARNING_THRESHOLD_PCT = 20.0
DEFAULT_THINK_TIME_SECONDS = 1.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_SMOKE_DURATION = "60s"
DEFAULT_LOAD_RAMP_UP_DURATION = "1m"
DEFAULT_LOAD_HOLD_DURATION = "5m"
DEFAULT_SOAK_DURATION = "30m"
DEFAULT_REGRESSION_THRESHOLD = 0.20
DEFAULT_NATS_URL = "nats://127.0.0.1:4222"
DEFAULT_NTFY_USERNAME = "alertmanager"
DEFAULT_NTFY_WARN_TOPIC = "platform.slo.warn"


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


def require_number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be numeric")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return number


def require_int(value: Any, path: str, *, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def current_commit(repo_root: Path) -> str:
    snapshot_commit = os.environ.get("LV3_SNAPSHOT_SOURCE_COMMIT", "").strip()
    if snapshot_commit:
        return snapshot_commit
    return run_git(repo_root, "rev-parse", "HEAD")


def current_repo_version(repo_root: Path) -> str:
    return (repo_root / "VERSION").read_text(encoding="utf-8").strip()


def run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def maybe_read_secret_path(repo_root: Path, secret_id: str) -> str | None:
    payload = load_json(repo_root / "config" / "controller-local-secrets.json")
    secret = require_mapping(payload.get("secrets"), "config/controller-local-secrets.json.secrets").get(secret_id)
    if not isinstance(secret, dict) or secret.get("kind") != "file":
        return None
    path = Path(require_str(secret.get("path"), f"secret '{secret_id}'.path")).expanduser()
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def load_service_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(repo_root / "config" / "service-capability-catalog.json")
    services = require_list(payload.get("services"), "config/service-capability-catalog.json.services")
    return {
        require_str(service.get("id"), f"service[{index}].id"): require_mapping(service, f"service[{index}]")
        for index, service in enumerate(services)
    }


def load_capacity_load_profiles(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(repo_root / "config" / "capacity-model.json")
    profiles = require_list(payload.get("service_load_profiles", []), "config/capacity-model.json.service_load_profiles")
    profile_index: dict[str, dict[str, Any]] = {}
    for index, raw_profile in enumerate(profiles):
        path = f"config/capacity-model.json.service_load_profiles[{index}]"
        profile = require_mapping(raw_profile, path)
        service_id = require_str(profile.get("service_id"), f"{path}.service_id")
        if service_id in profile_index:
            raise ValueError(f"duplicate load profile for service '{service_id}'")
        profile_index[service_id] = {
            "typical_concurrency": require_int(profile.get("typical_concurrency"), f"{path}.typical_concurrency", minimum=1),
            "smoke_vus": int(profile.get("smoke_vus", min(max(int(profile["typical_concurrency"]), 1), 3))),
            "request_timeout_seconds": float(profile.get("request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS)),
            "think_time_seconds": float(profile.get("think_time_seconds", DEFAULT_THINK_TIME_SECONDS)),
            "notes": profile.get("notes", ""),
        }
    return profile_index


def default_prometheus_remote_write_url(repo_root: Path) -> str:
    env_url = os.environ.get("LV3_K6_PROMETHEUS_REMOTE_WRITE_URL")
    if env_url:
        return env_url.rstrip("/")
    from platform.slo import default_prometheus_url

    url = default_prometheus_url(repo_root=repo_root)
    if not url:
        raise ValueError("Prometheus URL is not configured")
    return f"{url.rstrip('/')}/api/v1/write"


def default_nats_url(repo_root: Path) -> str:
    env_url = os.environ.get("LV3_NATS_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    nats_service = load_service_index(repo_root).get("nats")
    if isinstance(nats_service, dict):
        internal_url = nats_service.get("internal_url")
        if isinstance(internal_url, str) and internal_url.strip():
            return internal_url.rstrip("/")
    return DEFAULT_NATS_URL


def ensure_nats_url_reachable(nats_url: str, *, timeout_seconds: float = 1.0) -> None:
    parsed = urllib.parse.urlparse(nats_url)
    host = parsed.hostname
    port = parsed.port or 4222
    if not host:
        raise ValueError(f"invalid NATS URL '{nats_url}'")
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass
    except OSError as exc:
        raise RuntimeError(f"NATS endpoint unavailable at {nats_url}: {exc}") from exc


def relative_repo_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def load_target_url_overrides() -> dict[str, str]:
    raw = os.environ.get("LV3_K6_TARGET_URL_OVERRIDES", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:  # noqa: PERF203
        raise ValueError("LV3_K6_TARGET_URL_OVERRIDES must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("LV3_K6_TARGET_URL_OVERRIDES must be a JSON object")
    overrides: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("LV3_K6_TARGET_URL_OVERRIDES keys and values must be strings")
        if value.strip():
            overrides[key] = value.strip()
    return overrides


def build_targets(
    *,
    repo_root: Path,
    scenario: str,
    service_ids: list[str] | None,
    smoke_duration: str,
    load_ramp_up_duration: str,
    load_hold_duration: str,
    soak_duration: str,
    target_url_overrides: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    slo_catalog = load_slo_catalog(repo_root=repo_root)
    service_index = load_service_index(repo_root)
    load_profiles = load_capacity_load_profiles(repo_root)
    requested = set(service_ids or [])

    availability_slos = {
        entry["service_id"]: entry
        for entry in slo_catalog["slos"]
        if entry["indicator"] == "availability"
    }
    latency_slos = {
        entry["service_id"]: entry
        for entry in slo_catalog["slos"]
        if entry["indicator"] == "latency"
    }

    deduped_smoke_targets: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in slo_catalog["slos"]:
        service_id = entry["service_id"]
        if requested and service_id not in requested:
            continue
        key = (service_id, entry["target_url"])
        target = deduped_smoke_targets.setdefault(
            key,
            {
                "service_id": service_id,
                "service_name": require_str(service_index[service_id].get("name"), f"service '{service_id}'.name"),
                "target_url": entry["target_url"],
                "expected_status": [200],
                "method": "GET",
                "headers": {},
                "body": None,
                "follow_redirects": True,
                "max_error_rate": DEFAULT_MAX_ERROR_RATE,
                "latency_threshold_ms": None,
                "availability_slo_id": availability_slos.get(service_id, {}).get("id"),
                "availability_objective_percent": availability_slos.get(service_id, {}).get("objective_percent"),
                "latency_slo_id": latency_slos.get(service_id, {}).get("id"),
                "scenario_type": "smoke",
            },
        )
        override = (target_url_overrides or {}).get(service_id)
        if override:
            target["target_url"] = override
        if entry["indicator"] == "latency":
            target["latency_threshold_ms"] = float(entry["latency_threshold_ms"])

    if scenario == "smoke":
        targets = list(deduped_smoke_targets.values())
        for target in targets:
            profile = load_profiles.get(target["service_id"], {})
            target["vus"] = int(profile.get("smoke_vus", 1))
            target["duration"] = smoke_duration
            target["request_timeout_seconds"] = float(
                profile.get("request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS)
            )
            target["think_time_seconds"] = float(profile.get("think_time_seconds", DEFAULT_THINK_TIME_SECONDS))
        return sorted(targets, key=lambda item: item["service_id"])

    targets: list[dict[str, Any]] = []
    for service_id, latency_slo in latency_slos.items():
        if requested and service_id not in requested:
            continue
        if service_id not in load_profiles:
            continue
        profile = load_profiles[service_id]
        target = {
            "service_id": service_id,
            "service_name": require_str(service_index[service_id].get("name"), f"service '{service_id}'.name"),
            "target_url": latency_slo["target_url"],
            "expected_status": [200],
            "method": "GET",
            "headers": {},
            "body": None,
            "follow_redirects": True,
            "max_error_rate": DEFAULT_MAX_ERROR_RATE,
            "latency_threshold_ms": float(latency_slo["latency_threshold_ms"]),
            "availability_slo_id": availability_slos.get(service_id, {}).get("id"),
            "availability_objective_percent": availability_slos.get(service_id, {}).get("objective_percent"),
            "latency_slo_id": latency_slo["id"],
            "scenario_type": scenario,
            "vus": int(profile["typical_concurrency"]),
            "request_timeout_seconds": float(profile.get("request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS)),
            "think_time_seconds": float(profile.get("think_time_seconds", DEFAULT_THINK_TIME_SECONDS)),
            "ramp_up_duration": load_ramp_up_duration,
            "hold_duration": load_hold_duration,
            "duration": load_hold_duration,
        }
        override = (target_url_overrides or {}).get(service_id)
        if override:
            target["target_url"] = override
        targets.append(target)
    if not targets:
        raise ValueError(f"no k6 targets are configured for scenario '{scenario}'")
    return sorted(targets, key=lambda item: item["service_id"])


def write_run_config(
    *,
    repo_root: Path,
    run_id: str,
    scenario: str,
    targets: list[dict[str, Any]],
) -> Path:
    temp_dir = repo_root / ".local" / "k6"
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / f"{run_id}-{scenario}-config.json"
    path.write_text(json.dumps({"scenario": scenario, "services": targets}, indent=2) + "\n", encoding="utf-8")
    return path


def docker_workspace_mount_source(repo_root: Path) -> str:
    override = os.environ.get("LV3_DOCKER_WORKSPACE_PATH", "").strip()
    if override:
        return str(Path(override).resolve())
    return str(repo_root.resolve())


def docker_workspace_user() -> str:
    return f"{os.getuid()}:{os.getgid()}"


def run_k6(
    *,
    repo_root: Path,
    run_id: str,
    scenario: str,
    runner_context: str,
    environment: str,
    config_path: Path,
    summary_path: Path,
    prometheus_remote_write_url: str,
) -> tuple[int, str]:
    image_catalog = load_image_catalog()
    image_entry = require_mapping(image_catalog["images"].get("k6_runtime"), "config/image-catalog.json.images.k6_runtime")
    image_ref = require_str(image_entry.get("ref"), "config/image-catalog.json.images.k6_runtime.ref")
    workspace_mount_source = docker_workspace_mount_source(repo_root)
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "--volume",
        f"{workspace_mount_source}:{repo_root}",
        "--workdir",
        str(repo_root),
        "--user",
        docker_workspace_user(),
        "--env",
        f"LV3_K6_CONFIG_PATH={config_path}",
        "--env",
        f"K6_PROMETHEUS_RW_SERVER_URL={prometheus_remote_write_url}",
        "--env",
        "K6_PROMETHEUS_RW_TREND_STATS=p(95),avg,max",
        "--env",
        "K6_PROMETHEUS_RW_STALE_MARKERS=true",
        image_ref,
        "run",
        "--tag",
        f"testid={run_id}",
        "--tag",
        f"scenario_type={scenario}",
        "--tag",
        f"runner_context={runner_context}",
        "--tag",
        f"environment={environment}",
        "-o",
        "experimental-prometheus-rw",
        "--summary-export",
        str(summary_path),
        str(repo_root / "config" / "k6" / "scripts" / "http-slo-probe.js"),
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stderr.strip() or completed.stdout.strip()


def load_summary_metric(summary: dict[str, Any], metric_name: str, service_id: str) -> dict[str, Any]:
    target_key = f"{metric_name}{{service_id:{service_id}}}"
    metrics = require_mapping(summary.get("metrics"), "k6 summary.metrics")
    value = metrics.get(target_key)
    if isinstance(value, dict):
        return value
    for key, candidate in metrics.items():
        if not isinstance(candidate, dict):
            continue
        match = SUMMARY_KEY_PATTERN.match(str(key))
        if match and match.group("metric") == metric_name and match.group("service_id") == service_id:
            return candidate
    return {}


def metric_value(summary: dict[str, Any], metric_name: str, service_id: str, field: str, default: float = 0.0) -> float:
    metric = load_summary_metric(summary, metric_name, service_id)
    if field in metric and isinstance(metric[field], (int, float)) and not isinstance(metric[field], bool):
        return float(metric[field])
    values = metric.get("values", {})
    if isinstance(values, dict) and field in values:
        return float(values[field])
    return default


def service_request_counts(summary: dict[str, Any], service_id: str) -> tuple[int, int]:
    checks_metric = load_summary_metric(summary, "checks", service_id)
    passes = checks_metric.get("passes")
    fails = checks_metric.get("fails")
    if isinstance(passes, int) and isinstance(fails, int):
        return passes, fails

    success_count = int(metric_value(summary, "lv3_successful_requests", service_id, "count"))
    failed_count = int(metric_value(summary, "lv3_failed_requests", service_id, "count"))
    return success_count, failed_count


def build_regression_payload(
    *,
    repo_root: Path,
    receipts_dir: Path,
    scenario: str,
    service_id: str,
    current_p95_ms: float,
) -> dict[str, Any]:
    candidates = sorted(
        path
        for path in receipts_dir.glob(f"{scenario}-{service_id}-*.json")
        if path.is_file()
    )
    if not candidates:
        return {
            "checked": False,
            "baseline_receipt": None,
            "baseline_p95_ms": None,
            "current_p95_ms": current_p95_ms,
            "regression_ratio": None,
            "threshold_ratio": DEFAULT_REGRESSION_THRESHOLD,
            "regressed": False,
        }
    baseline_path = candidates[-1]
    baseline = load_json(baseline_path)
    baseline_p95_ms = float(baseline["metrics"]["http_req_duration_p95_ms"])
    if baseline_p95_ms <= 0:
        regression_ratio = None
        regressed = False
    else:
        regression_ratio = (current_p95_ms - baseline_p95_ms) / baseline_p95_ms
        regressed = regression_ratio > DEFAULT_REGRESSION_THRESHOLD
    return {
        "checked": True,
        "baseline_receipt": relative_repo_path(baseline_path, repo_root),
        "baseline_p95_ms": baseline_p95_ms,
        "current_p95_ms": current_p95_ms,
        "regression_ratio": regression_ratio,
        "threshold_ratio": DEFAULT_REGRESSION_THRESHOLD,
        "regressed": regressed,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def publish_regression_event(
    *,
    repo_root: Path,
    service_id: str,
    scenario: str,
    receipt_path: Path,
    regression: dict[str, Any],
) -> bool:
    if not regression["regressed"]:
        return False
    nats_url = default_nats_url(repo_root)
    ensure_nats_url_reachable(nats_url)
    publish_nats_events(
        [
            {
                "event": "platform.slo.k6_regression",
                "payload": {
                    "scenario": scenario,
                    "service_id": service_id,
                    "baseline_receipt": regression["baseline_receipt"],
                    "current_receipt": relative_repo_path(receipt_path, repo_root),
                    "baseline_p95_ms": regression["baseline_p95_ms"],
                    "current_p95_ms": regression["current_p95_ms"],
                    "regression_ratio": regression["regression_ratio"],
                    "threshold_ratio": regression["threshold_ratio"],
                    "recorded_at": isoformat(utc_now()),
                },
            }
        ],
        nats_url=nats_url,
        credentials=None,
    )
    return True


def notify_ntfy(
    *,
    repo_root: Path,
    service_id: str,
    scenario: str,
    budget_remaining_pct: float,
    receipt_path: Path,
) -> str | None:
    if budget_remaining_pct >= DEFAULT_WARNING_THRESHOLD_PCT:
        return None
    password = maybe_read_secret_path(repo_root, "ntfy_alertmanager_password")
    if not password:
        raise ValueError("ntfy_alertmanager_password is not available for k6 warning notification")
    ntfy_service = load_service_index(repo_root).get("ntfy")
    if ntfy_service is None:
        raise ValueError("service-capability-catalog.json is missing ntfy")
    base_url = require_str(ntfy_service.get("internal_url"), "ntfy.internal_url").rstrip("/")
    topic = DEFAULT_NTFY_WARN_TOPIC
    request = urllib.request.Request(
        f"{base_url}/{urllib.parse.quote(topic)}",
        data=(
            f"{service_id} {scenario} load-test warning: "
            f"{budget_remaining_pct:.1f}% error budget remaining "
            f"({relative_repo_path(receipt_path, repo_root)})"
        ).encode("utf-8"),
        method="POST",
        headers={
            "Title": f"LV3 k6 warning for {service_id}",
            "Priority": "default",
            "Authorization": "Basic "
            + (
                __import__("base64").b64encode(
                    f"{DEFAULT_NTFY_USERNAME}:{password}".encode("utf-8")
                ).decode("ascii")
            ),
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        if response.status >= 300:
            raise RuntimeError(f"ntfy notification failed with HTTP {response.status}")
    return topic


def build_receipts(
    *,
    repo_root: Path,
    scenario: str,
    runner_context: str,
    environment: str,
    recorded_at: dt.datetime,
    summary_path: Path,
    summary: dict[str, Any],
    targets: list[dict[str, Any]],
    output_dir: Path,
    publish_nats: bool,
    notify_ntfy_flag: bool,
) -> list[Path]:
    receipts: list[Path] = []
    image_ref = require_mapping(load_image_catalog()["images"]["k6_runtime"], "k6_runtime")["ref"]
    for target in targets:
        service_id = target["service_id"]
        success_count, failed_count = service_request_counts(summary, service_id)
        request_count = success_count + failed_count
        error_rate = (failed_count / request_count) if request_count else 0.0
        p95_ms = metric_value(summary, "http_req_duration", service_id, "p(95)")
        avg_ms = metric_value(summary, "http_req_duration", service_id, "avg")
        max_ms = metric_value(summary, "http_req_duration", service_id, "max")
        latency_threshold_ms = target.get("latency_threshold_ms")
        latency_passed = latency_threshold_ms is None or p95_ms <= float(latency_threshold_ms)
        availability_objective = target.get("availability_objective_percent")
        if availability_objective is None:
            error_budget_consumed_pct = 0.0 if error_rate == 0 else 100.0
        else:
            availability_slo = {"objective_percent": availability_objective}
            budget_ratio = error_budget_ratio(availability_slo)
            error_budget_consumed_pct = min((error_rate / budget_ratio) * 100.0, 100.0) if budget_ratio > 0 else 100.0
        error_budget_remaining_pct = max(0.0, 100.0 - error_budget_consumed_pct)

        metric_failures: list[str] = []
        failure_reasons: list[str] = []
        if error_rate > DEFAULT_MAX_ERROR_RATE:
            metric_failures.append(
                f"error rate {error_rate:.4f} exceeded {DEFAULT_MAX_ERROR_RATE:.4f}"
            )
        if not latency_passed and latency_threshold_ms is not None:
            metric_failures.append(
                f"p95 latency {p95_ms:.2f}ms exceeded {float(latency_threshold_ms):.2f}ms"
            )
        failure_reasons.extend(metric_failures)

        regression = build_regression_payload(
            repo_root=repo_root,
            receipts_dir=output_dir,
            scenario=scenario,
            service_id=service_id,
            current_p95_ms=p95_ms,
        )
        receipt_id = f"{recorded_at.date().isoformat()}-{scenario}-{service_id}-{recorded_at.strftime('%H%M%SZ')}"
        receipt_path = output_dir / f"{scenario}-{service_id}-{recorded_at.strftime('%Y%m%dT%H%M%SZ')}.json"

        nats_published = False
        ntfy_topic = None
        if publish_nats:
            try:
                nats_published = publish_regression_event(
                    repo_root=repo_root,
                    service_id=service_id,
                    scenario=scenario,
                    receipt_path=receipt_path,
                    regression=regression,
                )
            except Exception as exc:  # noqa: BLE001
                failure_reasons.append(f"nats regression notification unavailable: {exc}")
                print(
                    f"k6 receipt warning for {service_id}: failed to publish NATS regression event: {exc}",
                    file=sys.stderr,
                )
        if notify_ntfy_flag:
            try:
                ntfy_topic = notify_ntfy(
                    repo_root=repo_root,
                    service_id=service_id,
                    scenario=scenario,
                    budget_remaining_pct=error_budget_remaining_pct,
                    receipt_path=receipt_path,
                )
            except Exception as exc:  # noqa: BLE001
                failure_reasons.append(f"ntfy notification unavailable: {exc}")
                print(
                    f"k6 receipt warning for {service_id}: failed to deliver ntfy warning: {exc}",
                    file=sys.stderr,
                )

        receipt = {
            "$schema": "docs/schema/k6-receipt.schema.json",
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "receipt_id": receipt_id,
            "scenario": scenario,
            "service_id": service_id,
            "service_name": target["service_name"],
            "target_url": target["target_url"],
            "environment": environment,
            "runner_context": runner_context,
            "recorded_on": recorded_at.date().isoformat(),
            "recorded_at": isoformat(recorded_at),
            "recorded_by": os.environ.get("USER", "codex"),
            "source_commit": current_commit(repo_root),
            "repo_version_context": current_repo_version(repo_root),
            "k6_image_ref": image_ref,
            "summary_export": relative_repo_path(summary_path, repo_root),
            "prometheus_remote_write_url": default_prometheus_remote_write_url(repo_root),
            "scenario_config": {
                "vus": target["vus"],
                "duration": target.get("duration"),
                "ramp_up_duration": target.get("ramp_up_duration"),
                "hold_duration": target.get("hold_duration"),
                "max_error_rate": DEFAULT_MAX_ERROR_RATE,
                "think_time_seconds": target["think_time_seconds"],
                "request_timeout_seconds": target["request_timeout_seconds"],
                "latency_threshold_ms": latency_threshold_ms,
            },
            "metrics": {
                "request_count": request_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "error_rate": error_rate,
                "http_req_duration_p95_ms": p95_ms,
                "http_req_duration_avg_ms": avg_ms,
                "http_req_duration_max_ms": max_ms,
            },
            "slo_assessment": {
                "availability_slo_id": target.get("availability_slo_id"),
                "latency_slo_id": target.get("latency_slo_id"),
                "latency_threshold_ms": latency_threshold_ms,
                "availability_objective_percent": availability_objective,
                "error_budget_consumed_pct": error_budget_consumed_pct,
                "error_budget_remaining_pct": error_budget_remaining_pct,
                "error_budget_warning_threshold_pct": DEFAULT_WARNING_THRESHOLD_PCT,
                "within_error_budget": error_budget_remaining_pct >= DEFAULT_WARNING_THRESHOLD_PCT,
                "latency_threshold_passed": latency_passed,
            },
            "regression": regression,
            "notifications": {
                "nats_event_published": nats_published,
                "ntfy_topic_notified": ntfy_topic,
            },
            "result": "failed" if metric_failures else "passed",
            "failure_reasons": failure_reasons,
        }
        write_json(receipt_path, receipt)
        receipts.append(receipt_path)
    return receipts


def validate_k6_receipt(
    receipt: dict[str, Any],
    path: Path,
    service_index: dict[str, dict[str, Any]],
    repo_root: Path,
) -> None:
    schema = load_json(K6_RECEIPT_SCHEMA_PATH)
    required = require_list(schema.get("required"), f"{K6_RECEIPT_SCHEMA_PATH}.required")
    for key in required:
        if key not in receipt:
            raise ValueError(f"{path}: missing required key '{key}'")
    if receipt.get("$schema") != "docs/schema/k6-receipt.schema.json":
        raise ValueError(f"{path}: invalid $schema")
    if receipt.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"{path}: schema_version must be {SUPPORTED_SCHEMA_VERSION}")
    scenario = require_str(receipt.get("scenario"), f"{path}.scenario")
    if scenario not in {"smoke", "load", "soak"}:
        raise ValueError(f"{path}.scenario must be smoke, load, or soak")
    service_id = require_str(receipt.get("service_id"), f"{path}.service_id")
    if service_id not in service_index:
        raise ValueError(f"{path}.service_id references unknown service '{service_id}'")
    metrics = require_mapping(receipt.get("metrics"), f"{path}.metrics")
    request_count = require_int(metrics.get("request_count"), f"{path}.metrics.request_count", minimum=0)
    success_count = require_int(metrics.get("success_count"), f"{path}.metrics.success_count", minimum=0)
    failed_count = require_int(metrics.get("failed_count"), f"{path}.metrics.failed_count", minimum=0)
    if success_count + failed_count != request_count:
        raise ValueError(f"{path}.metrics request counts must add up")
    require_number(metrics.get("error_rate"), f"{path}.metrics.error_rate", minimum=0)
    summary_export = Path(require_str(receipt.get("summary_export"), f"{path}.summary_export"))
    if not summary_export.is_absolute():
        summary_export = repo_root / summary_export
    if not summary_export.exists():
        raise ValueError(f"{path}.summary_export references missing file '{summary_export}'")


def validate_k6_receipts(repo_root: Path, receipts_dir: Path | None = None, *, quiet: bool = False) -> int:
    service_index = load_service_index(repo_root)
    target_dir = receipts_dir or (repo_root / "receipts" / "k6")
    count = 0
    for path in sorted(target_dir.glob("*.json")):
        receipt = load_json(path)
        validate_k6_receipt(receipt, path, service_index, repo_root)
        count += 1
    if not quiet:
        print(f"k6 receipts OK: {target_dir} ({count} file(s))")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or validate the repo-managed k6 load-testing path.")
    parser.add_argument("--validate", action="store_true", help="Validate committed k6 receipts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repo checkout root.")
    parser.add_argument("--scenario", choices=["smoke", "load", "soak"], help="Scenario to run.")
    parser.add_argument("--service", action="append", dest="services", help="Optional service_id filter.")
    parser.add_argument("--output-dir", default=str(K6_RECEIPTS_DIR), help="Receipt output directory.")
    parser.add_argument("--runner-context", default="manual", help="Runner context label.")
    parser.add_argument("--environment", default="production", help="Target environment label.")
    parser.add_argument("--publish-nats", action="store_true", help="Publish platform.slo.k6_regression when a load regression is detected.")
    parser.add_argument("--notify-ntfy", action="store_true", help="Notify the ntfy warning topic when error budget remaining drops below 20 percent.")
    parser.add_argument("--smoke-duration", default=DEFAULT_SMOKE_DURATION, help="Smoke duration override.")
    parser.add_argument("--load-ramp-up-duration", default=DEFAULT_LOAD_RAMP_UP_DURATION, help="Load ramp-up duration override.")
    parser.add_argument("--load-hold-duration", default=DEFAULT_LOAD_HOLD_DURATION, help="Load hold duration override.")
    parser.add_argument("--soak-duration", default=DEFAULT_SOAK_DURATION, help="Soak duration override.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.validate:
        return validate_k6_receipts(repo_root)
    if not args.scenario:
        parser.error("--scenario is required unless --validate is used")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "raw").mkdir(parents=True, exist_ok=True)

    recorded_at = utc_now()
    run_id = recorded_at.strftime("%Y%m%dT%H%M%SZ")
    target_url_overrides = load_target_url_overrides()
    targets = build_targets(
        repo_root=repo_root,
        scenario=args.scenario,
        service_ids=args.services,
        smoke_duration=args.smoke_duration,
        load_ramp_up_duration=args.load_ramp_up_duration,
        load_hold_duration=args.load_hold_duration,
        soak_duration=args.soak_duration,
        target_url_overrides=target_url_overrides,
    )
    config_path = write_run_config(repo_root=repo_root, run_id=run_id, scenario=args.scenario, targets=targets)
    summary_path = output_dir / "raw" / f"{run_id}-{args.scenario}-summary.json"
    prometheus_remote_write_url = default_prometheus_remote_write_url(repo_root)
    returncode, output = run_k6(
        repo_root=repo_root,
        run_id=run_id,
        scenario=args.scenario,
        runner_context=args.runner_context,
        environment=args.environment,
        config_path=config_path,
        summary_path=summary_path,
        prometheus_remote_write_url=prometheus_remote_write_url,
    )
    if returncode != 0 and not summary_path.exists():
        print(output, file=sys.stderr)
        return returncode
    summary = load_json(summary_path)
    receipts = build_receipts(
        repo_root=repo_root,
        scenario=args.scenario,
        runner_context=args.runner_context,
        environment=args.environment,
        recorded_at=recorded_at,
        summary_path=summary_path,
        summary=summary,
        targets=targets,
        output_dir=output_dir,
        publish_nats=args.publish_nats,
        notify_ntfy_flag=args.notify_ntfy,
    )
    if returncode != 0:
        print(output, file=sys.stderr)
    print(
        json.dumps(
            {
                "status": "ok" if returncode == 0 else "failed",
                "scenario": args.scenario,
                "runner_context": args.runner_context,
                "services": [target["service_id"] for target in targets],
                "receipts": [str(path.relative_to(repo_root)) for path in receipts],
                "summary_export": str(summary_path.relative_to(repo_root)),
            },
            indent=2,
        )
    )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
