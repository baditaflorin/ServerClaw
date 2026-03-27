#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import uuid

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, write_json
from dns_drift import collect_drift as collect_dns_drift
from docker_image_drift import collect_drift as collect_docker_image_drift
from drift_lib import (
    drift_event_topic,
    isoformat,
    load_controller_context,
    nats_tunnel,
    publish_nats_events,
    resolve_nats_credentials,
    utc_now,
    workstream_suppression,
)
from parse_ansible_drift import parse_ansible_output
from run_namespace import ensure_run_namespace, resolve_run_namespace
from tls_cert_drift import collect_drift as collect_tls_drift


REPO_ROOT = repo_path()
DEFAULT_RECEIPT_DIR = repo_path("receipts", "drift-reports")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
HEALTH_PROBE_CATALOG_PATH = repo_path("config", "health-probe-catalog.json")


def parse_tofu_plan(plan_json_path: Path) -> list[dict[str, Any]]:
    if not plan_json_path.exists():
        return []
    payload = load_json(plan_json_path)
    changes = payload.get("resource_changes", [])
    records: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        change_block = change.get("change", {})
        actions = change_block.get("actions", [])
        if not isinstance(actions, list) or actions == ["no-op"]:
            continue
        address = str(change.get("address", "unknown"))
        after = change_block.get("after")
        before = change_block.get("before")
        records.append(
            {
                "source": "tofu",
                "event": drift_event_topic("warn"),
                "severity": "warn",
                "resource": address,
                "detail": f"planned actions: {', '.join(actions)}",
                "actions": actions,
                "before": before,
                "after": after,
                "shared_surfaces": [address],
            }
        )
    return records


def run_tofu_drift(environment: str, *, command: str | None = None) -> list[dict[str, Any]]:
    run_namespace = ensure_run_namespace(
        resolve_run_namespace(
            repo_root=REPO_ROOT,
            run_id=f"drift-tofu-{environment}-{uuid.uuid4().hex}",
        )
    )
    drift_command = command or f"./scripts/tofu_exec.sh drift {shlex.quote(environment)}"
    env = os.environ.copy()
    env.setdefault("LV3_RUN_ID", run_namespace.run_id)
    env.setdefault("LV3_RUN_SLUG", run_namespace.run_slug)
    env.setdefault("LV3_RUN_NAMESPACE_ROOT", run_namespace.root)
    env.setdefault("LV3_RUN_TOFU_DIR", run_namespace.tofu_dir)
    result = subprocess.run(
        ["/bin/bash", "-lc", drift_command],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    plan_json = Path(run_namespace.tofu_dir) / f"{environment}.plan.json"
    records = parse_tofu_plan(plan_json)
    if result.returncode not in {0, 2}:
        message = result.stderr.strip() or result.stdout.strip() or "tofu drift command failed"
        records.append(
            {
                "source": "tofu",
                "event": drift_event_topic("critical"),
                "severity": "critical",
                "resource": f"tofu/{environment}",
                "detail": message,
                "shared_surfaces": [f"tofu/{environment}"],
            }
        )
    return records


def run_ansible_drift(environment: str, *, playbook: str, inventory: str, limit: str | None = None) -> list[dict[str, Any]]:
    del environment
    run_namespace = ensure_run_namespace(
        resolve_run_namespace(
            repo_root=REPO_ROOT,
            run_id=f"drift-ansible-{uuid.uuid4().hex}",
        )
    )
    command = [
        "ansible-playbook",
        "-i",
        inventory,
        playbook,
        "--check",
        "--diff",
    ]
    if limit:
        command.extend(["-l", limit])
    env = os.environ.copy()
    env.setdefault("LV3_RUN_ID", run_namespace.run_id)
    env.setdefault("LV3_RUN_SLUG", run_namespace.run_slug)
    env.setdefault("LV3_RUN_NAMESPACE_ROOT", run_namespace.root)
    env.setdefault("LV3_RUN_ANSIBLE_DIR", run_namespace.ansible_dir)
    env.setdefault("LV3_RUN_ANSIBLE_TMP_DIR", run_namespace.ansible_tmp_dir)
    env.setdefault("LV3_RUN_ANSIBLE_RETRY_DIR", run_namespace.ansible_retry_dir)
    env.setdefault("LV3_RUN_ANSIBLE_CONTROL_PATH_DIR", run_namespace.ansible_control_path_dir)
    env.setdefault("LV3_RUN_LOGS_DIR", run_namespace.logs_dir)
    env.setdefault("LV3_RUN_ANSIBLE_LOG_PATH", run_namespace.ansible_log_path)
    env.setdefault("ANSIBLE_STDOUT_CALLBACK", "json")
    env.setdefault("ANSIBLE_LOCAL_TEMP", run_namespace.ansible_tmp_dir)
    env.setdefault("ANSIBLE_RETRY_FILES_SAVE_PATH", run_namespace.ansible_retry_dir)
    env.setdefault("ANSIBLE_SSH_CONTROL_PATH_DIR", run_namespace.ansible_control_path_dir)
    env.setdefault("ANSIBLE_LOG_PATH", run_namespace.ansible_log_path)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = result.stdout if result.stdout.strip() else result.stderr
    records = parse_ansible_output(payload)
    if result.returncode not in {0, 2, 4} and not records:
        records.append(
            {
                "source": "ansible-check-mode",
                "event": drift_event_topic("critical"),
                "severity": "critical",
                "resource": playbook,
                "detail": result.stderr.strip() or result.stdout.strip() or "ansible check failed",
                "shared_surfaces": [playbook],
            }
        )
    return records


def load_service_map() -> dict[str, dict[str, Any]]:
    payload = load_json(SERVICE_CATALOG_PATH)
    return {service["id"]: service for service in payload.get("services", [])}


def load_health_probe_catalog() -> dict[str, Any]:
    payload = load_json(HEALTH_PROBE_CATALOG_PATH)
    return payload.get("services", {})


def http_probe(url: str, *, timeout: float, validate_tls: bool) -> bool:
    context = None
    if url.startswith("https://") and not validate_tls:
        context = ssl._create_unverified_context()
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return 200 <= response.status < 400


def tcp_probe(host: str, port: int, *, timeout: float) -> bool:
    with socket.create_connection((host, port), timeout=timeout):
        return True


def service_is_healthy(service: dict[str, Any], health_probes: dict[str, Any], *, timeout: float = 3.0) -> bool:
    probe = health_probes.get(service.get("health_probe_id"), {})
    readiness = probe.get("readiness") if isinstance(probe, dict) else None
    url = service.get("public_url") or service.get("internal_url")
    if isinstance(url, str) and url:
        parsed = urlparse(url)
        try:
            if parsed.scheme in {"http", "https"}:
                validate_tls = True
                if isinstance(readiness, dict) and isinstance(readiness.get("validate_tls"), bool):
                    validate_tls = readiness["validate_tls"]
                return http_probe(url, timeout=timeout, validate_tls=validate_tls)
            if parsed.scheme == "ssh":
                return tcp_probe(parsed.hostname or "127.0.0.1", parsed.port or 22, timeout=timeout)
        except Exception:  # noqa: BLE001
            return False
    if isinstance(readiness, dict) and readiness.get("kind") == "tcp":
        try:
            return tcp_probe(str(readiness.get("host")), int(readiness.get("port")), timeout=timeout)
        except Exception:  # noqa: BLE001
            return False
    return True


def backoff_health(service_id: str, service_map: dict[str, dict[str, Any]], health_probes: dict[str, Any]) -> bool:
    service = service_map.get(service_id)
    if service is None:
        return True
    for timeout in (1.0, 2.0, 4.0):
        if service_is_healthy(service, health_probes, timeout=timeout):
            return True
    return False


def enrich_records(records: list[dict[str, Any]], *, service_map: dict[str, dict[str, Any]], health_probes: dict[str, Any]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    detected_at = isoformat(utc_now())
    for record in records:
        item = dict(record)
        service_id = str(item.get("service") or "")
        if item.get("severity") == "warn" and service_id and not backoff_health(service_id, service_map, health_probes):
            item["severity"] = "critical"
            item["event"] = drift_event_topic("critical")
            item["detail"] = f"{item['detail']} (service unhealthy after backoff)"
        suppressed, matches = workstream_suppression([str(value) for value in item.get("shared_surfaces", []) if value])
        item["workstream_suppressed"] = suppressed
        if matches:
            item["suppressed_by"] = matches
        item["detected_at"] = detected_at
        item.setdefault("event", drift_event_topic(str(item["severity"])))
        enriched.append(item)
    return enriched


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counts = Counter(str(record.get("severity", "unknown")) for record in records)
    source_counts = Counter(str(record.get("source", "unknown")) for record in records)
    unsuppressed = [record for record in records if not record.get("workstream_suppressed")]
    return {
        "record_count": len(records),
        "unsuppressed_count": len(unsuppressed),
        "warn_count": severity_counts.get("warn", 0),
        "critical_count": severity_counts.get("critical", 0),
        "suppressed_count": sum(1 for record in records if record.get("workstream_suppressed")),
        "source_counts": dict(sorted(source_counts.items())),
        "status": "critical"
        if any(record.get("severity") == "critical" and not record.get("workstream_suppressed") for record in records)
        else "warn"
        if any(record.get("severity") == "warn" and not record.get("workstream_suppressed") for record in records)
        else "clean",
        "status_code": 2
        if any(record.get("severity") == "critical" and not record.get("workstream_suppressed") for record in records)
        else 1
        if any(record.get("severity") == "warn" and not record.get("workstream_suppressed") for record in records)
        else 0,
    }


def print_summary_table(records: list[dict[str, Any]]) -> None:
    if not records:
        print("SOURCE               RESOURCE                         SEVERITY  SUPPRESSED  DETAIL")
        print("clean                <none>                           ok        no          no drift detected")
        return
    print("SOURCE               RESOURCE                         SEVERITY  SUPPRESSED  DETAIL")
    for record in records:
        print(
            f"{str(record.get('source', ''))[:20]:<20} "
            f"{str(record.get('resource') or record.get('service') or '')[:32]:<32} "
            f"{str(record.get('severity', '')):<9} "
            f"{'yes' if record.get('workstream_suppressed') else 'no':<11} "
            f"{str(record.get('detail', ''))[:120]}"
        )


def maybe_publish_nats(records: list[dict[str, Any]], *, publish: bool, context: dict[str, Any] | None = None) -> None:
    if not publish:
        return
    events = [
        record
        for record in records
        if record.get("event", "").startswith("platform.drift.")
        and record.get("severity") in {"warn", "critical"}
    ]
    if not events:
        return
    controller_context = context or load_controller_context()
    nats_url = os.environ.get("LV3_NATS_URL", "").strip()
    credentials = resolve_nats_credentials(controller_context)
    if nats_url:
        publish_nats_events(events, nats_url=nats_url, credentials=credentials)
        return
    with nats_tunnel(controller_context) as local_port:
        publish_nats_events(events, nats_url=f"nats://127.0.0.1:{local_port}", credentials=credentials)


def maybe_write_metrics(summary: dict[str, Any]) -> None:
    influx_url = os.environ.get("DRIFT_INFLUXDB_URL", "").strip()
    influx_bucket = os.environ.get("DRIFT_INFLUXDB_BUCKET", "").strip()
    influx_org = os.environ.get("DRIFT_INFLUXDB_ORG", "").strip()
    influx_token = os.environ.get("DRIFT_INFLUXDB_TOKEN", "").strip()
    if not all((influx_url, influx_bucket, influx_org, influx_token)):
        return
    line = (
        f"platform_drift_summary,environment={os.environ.get('DRIFT_ENVIRONMENT', 'production')} "
        f"status_code={summary['status_code']}i,"
        f"unsuppressed_count={summary['unsuppressed_count']}i,"
        f"warn_count={summary['warn_count']}i,"
        f"critical_count={summary['critical_count']}i,"
        f"suppressed_count={summary['suppressed_count']}i"
    )
    request = urllib.request.Request(
        f"{influx_url.rstrip('/')}/api/v2/write?org={urllib.parse.quote(influx_org)}&bucket={urllib.parse.quote(influx_bucket)}&precision=s",
        data=line.encode("utf-8"),
        headers={"Authorization": f"Token {influx_token}", "Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            return
    except urllib.error.URLError as exc:
        raise RuntimeError(f"failed to write drift metrics: {exc}") from exc


def write_receipt(receipt_dir: Path, report: dict[str, Any]) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    path = receipt_dir / f"{timestamp}.json"
    write_json(path, report, indent=2, sort_keys=True)
    return path


def build_report(records: list[dict[str, Any]], *, environment: str) -> dict[str, Any]:
    summary = build_summary(records)
    return {
        "generated_at": isoformat(utc_now()),
        "environment": environment,
        "summary": summary,
        "records": records,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full LV3 drift-detection suite.")
    parser.add_argument("--env", default="production", choices=["production", "staging"])
    parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--playbook", default="playbooks/site.yml")
    parser.add_argument("--inventory", default="inventory/hosts.yml")
    parser.add_argument("--limit")
    parser.add_argument("--skip-tofu", action="store_true")
    parser.add_argument("--skip-ansible", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--skip-dns", action="store_true")
    parser.add_argument("--skip-tls", action="store_true")
    parser.add_argument("--publish-nats", action="store_true")
    parser.add_argument("--print-report-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        records: list[dict[str, Any]] = []
        context: dict[str, Any] | None = None
        if not args.skip_tofu:
            records.extend(run_tofu_drift(args.env))
        if not args.skip_ansible:
            records.extend(run_ansible_drift(args.env, playbook=args.playbook, inventory=args.inventory, limit=args.limit))
        if not args.skip_docker:
            context = load_controller_context()
            records.extend(collect_docker_image_drift(context))
        if not args.skip_dns:
            records.extend(collect_dns_drift())
        if not args.skip_tls:
            records.extend(collect_tls_drift())

        service_map = load_service_map()
        health_probes = load_health_probe_catalog()
        records = enrich_records(records, service_map=service_map, health_probes=health_probes)
        report = build_report(records, environment=args.env)
        receipt_path = write_receipt(args.receipt_dir, report)
        maybe_publish_nats(records, publish=args.publish_nats, context=context)
        maybe_write_metrics(report["summary"])

        print_summary_table(records)
        print(f"\nReceipt: {receipt_path}")
        if args.print_report_json:
            print(f"REPORT_JSON={json.dumps(report, separators=(',', ':'))}")

        status = report["summary"]["status"]
        if status == "clean":
            return 0
        if status == "warn":
            return 2
        return 1
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("drift detector", exc)


if __name__ == "__main__":
    raise SystemExit(main())
