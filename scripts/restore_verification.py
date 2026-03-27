#!/usr/bin/env python3
"""Restore Proxmox PBS backups into ephemeral VMs and run smoke tests."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, write_json
from drift_lib import (
    build_host_ssh_command,
    isoformat,
    load_controller_context,
    nats_tunnel,
    publish_nats_events,
    resolve_nats_credentials,
    run_command,
    utc_now,
)
from mutation_audit import build_event, emit_event_best_effort
from smoke_tests import backup_vm_smoke, docker_runtime_smoke, postgres_smoke
import synthetic_transaction_replay


DEFAULT_RECEIPT_DIR = repo_path("receipts", "restore-verifications")
FIXTURE_DEFINITIONS_DIR = repo_path("tests", "fixtures")
HEALTH_PROBE_CATALOG_PATH = repo_path("config", "health-probe-catalog.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
STORAGE_ID = "lv3-backup-pbs"
ALLOWED_SELECTION_STRATEGIES = {"latest", "random"}


@dataclass(frozen=True)
class RestoreTarget:
    vm_name: str
    source_vmid: int
    target_vmid: int
    bridge: str
    ip_cidr: str
    gateway: str
    mac_address: str
    smoke_kind: str


@dataclass(frozen=True)
class CommandOutcome:
    command: str
    returncode: int
    stdout: str
    stderr: str


def load_fixture_definition(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
            raise RuntimeError(
                "Missing dependency: PyYAML. Run via 'uv run --with pyyaml ...'."
            ) from exc
        payload = yaml.safe_load(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"fixture definition must be an object: {path}")
        return payload


def parse_pvesm_rows(payload: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in payload.splitlines():
        if not line.strip() or line.startswith("Volid"):
            continue
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 5:
            continue
        rows.append(
            {
                "volid": parts[0],
                "format": parts[1],
                "type": parts[2],
                "size": parts[3],
                "vmid": parts[4],
            }
        )
    return rows


def extract_backup_timestamp(volid: str):
    match = re.search(r"/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$", volid)
    if match is None:
        return None
    return __import__("datetime").datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))


def compact_timestamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def load_restore_targets() -> list[RestoreTarget]:
    context = load_controller_context()
    guest_map = {guest["name"]: guest for guest in context["host_vars"]["proxmox_guests"]}
    fixture_map = {
        "docker-runtime-lv3": load_fixture_definition(FIXTURE_DEFINITIONS_DIR / "docker-host-fixture.yml"),
        "postgres-lv3": load_fixture_definition(FIXTURE_DEFINITIONS_DIR / "postgres-host-fixture.yml"),
        "backup-lv3": load_fixture_definition(FIXTURE_DEFINITIONS_DIR / "ops-base-fixture.yml"),
    }
    vmid_map = {"postgres-lv3": 900, "docker-runtime-lv3": 901, "backup-lv3": 902}
    smoke_map = {
        "postgres-lv3": "postgres",
        "docker-runtime-lv3": "docker-runtime",
        "backup-lv3": "backup-vm",
    }

    targets: list[RestoreTarget] = []
    for vm_name in ("postgres-lv3", "docker-runtime-lv3", "backup-lv3"):
        guest = guest_map[vm_name]
        fixture = fixture_map[vm_name]
        targets.append(
            RestoreTarget(
                vm_name=vm_name,
                source_vmid=int(guest["vmid"]),
                target_vmid=vmid_map[vm_name],
                bridge=str(fixture["network"]["bridge"]),
                ip_cidr=str(fixture["network"]["ip_cidr"]),
                gateway=str(fixture["network"]["gateway"]),
                mac_address=str(guest["macaddr"]),
                smoke_kind=smoke_map[vm_name],
            )
        )
    return targets


def select_restore_targets(selected_names: list[str] | None = None) -> list[RestoreTarget]:
    targets = load_restore_targets()
    if not selected_names:
        return targets
    requested = {item.strip() for item in selected_names if item.strip()}
    if not requested:
        return targets
    filtered = [target for target in targets if target.vm_name in requested]
    missing = sorted(requested - {target.vm_name for target in filtered})
    if missing:
        raise ValueError(f"unknown restore-verification target(s): {', '.join(missing)}")
    return filtered


def run_host_command(context: dict[str, Any], command: str) -> CommandOutcome:
    argv = build_host_ssh_command(context, command)
    completed = run_command(argv)
    return CommandOutcome(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def require_host_command(context: dict[str, Any], command: str, *, action: str) -> CommandOutcome:
    outcome = run_host_command(context, command)
    if outcome.returncode == 0:
        return outcome
    detail = outcome.stderr or outcome.stdout or command
    raise RuntimeError(f"{action}: {detail}")


def build_restored_guest_ssh_command(context: dict[str, Any], ip_address: str, remote_command: str) -> list[str]:
    key_path = str(context["bootstrap_key"])
    host_login = f"{context['host_user']}@{context['host_addr']}"
    proxy_command = (
        f"ssh -i {shlex.quote(key_path)} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 "
        f"-o LogLevel=ERROR {shlex.quote(host_login)} -W %h:%p"
    )
    return [
        "ssh",
        "-i",
        key_path,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        f"ProxyCommand={proxy_command}",
        f"{context['host_user']}@{ip_address}",
        remote_command,
    ]


def run_restored_guest_command(context: dict[str, Any], ip_address: str, command: str) -> CommandOutcome:
    argv = build_restored_guest_ssh_command(context, ip_address, command)
    completed = run_command(argv)
    return CommandOutcome(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_restored_guest_agent_command(
    context: dict[str, Any],
    target_vmid: int,
    command: str,
    *,
    timeout_seconds: int = 30,
) -> CommandOutcome:
    outcome = run_host_command(
        context,
        f"sudo qm guest exec {target_vmid} --timeout {timeout_seconds} -- /bin/bash -lc {shlex.quote(command)}",
    )
    if outcome.returncode != 0:
        return CommandOutcome(
            command=command,
            returncode=outcome.returncode,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
        )
    payload = json.loads(outcome.stdout or "{}")
    return CommandOutcome(
        command=command,
        returncode=int(payload.get("exitcode", 1)),
        stdout=str(payload.get("out-data", "")).strip(),
        stderr=str(payload.get("err-data", "")).strip(),
    )


def guest_agent_ready(context: dict[str, Any], target_vmid: int) -> bool:
    return run_host_command(context, f"sudo qm agent {target_vmid} ping").returncode == 0


def wait_for_guest_access(
    context: dict[str, Any],
    target: RestoreTarget,
    *,
    timeout_seconds: int,
) -> tuple[str, int]:
    started = time.monotonic()
    deadline = started + timeout_seconds
    ip_address = target.ip_cidr.split("/", 1)[0]
    while time.monotonic() < deadline:
        outcome = run_restored_guest_command(context, ip_address, "true")
        if outcome.returncode == 0:
            return "ssh", int(time.monotonic() - started)
        if guest_agent_ready(context, target.target_vmid):
            qga_outcome = run_restored_guest_agent_command(context, target.target_vmid, "true")
            if qga_outcome.returncode == 0:
                return "qga", int(time.monotonic() - started)
        time.sleep(5)
    raise RuntimeError(
        f"Neither SSH nor qga became ready for restored guest {target.vm_name} ({ip_address})"
    )


def list_backups_for_vmid(context: dict[str, Any], source_vmid: int) -> list[dict[str, Any]]:
    outcome = require_host_command(
        context,
        f"sudo pvesm list {STORAGE_ID}",
        action=f"list backups for VMID {source_vmid}",
    )
    rows = parse_pvesm_rows(outcome.stdout)
    backups: list[dict[str, Any]] = []
    for row in rows:
        if row["vmid"] != str(source_vmid):
            continue
        timestamp = extract_backup_timestamp(row["volid"])
        if timestamp is None:
            continue
        backups.append({**row, "timestamp": timestamp})
    backups.sort(key=lambda item: item["timestamp"], reverse=True)
    return backups


def select_backup(
    backups: list[dict[str, Any]],
    *,
    lookback_days: int,
    selection_strategy: str,
    rng: random.Random,
) -> dict[str, Any]:
    if selection_strategy not in ALLOWED_SELECTION_STRATEGIES:
        raise ValueError(f"unsupported selection strategy: {selection_strategy}")

    cutoff = utc_now() - timedelta(days=lookback_days)
    eligible = [backup for backup in backups if backup["timestamp"] >= cutoff]
    candidates = eligible or backups
    if not candidates:
        raise RuntimeError("no PBS backups available")

    if selection_strategy == "latest":
        return candidates[0]
    return rng.choice(candidates)


def destroy_restored_vm(context: dict[str, Any], target_vmid: int) -> None:
    run_host_command(
        context,
        (
            f"if sudo qm status {target_vmid} >/dev/null 2>&1; then "
            f"sudo qm stop {target_vmid} --skiplock 1 >/dev/null 2>&1 || true; "
            f"sudo qm destroy {target_vmid} --purge 1 --skiplock 1 >/dev/null 2>&1 || true; "
            "fi"
        ),
    )


def restore_backup(context: dict[str, Any], target: RestoreTarget, backup: dict[str, Any]) -> int:
    destroy_restored_vm(context, target.target_vmid)
    started = time.monotonic()
    require_host_command(
        context,
        (
            f"sudo qmrestore {shlex.quote(backup['volid'])} {target.target_vmid} "
            "--storage local --unique 1"
        ),
        action=f"restore {target.vm_name}",
    )
    return int(time.monotonic() - started)


def configure_restored_vm(context: dict[str, Any], target: RestoreTarget) -> None:
    ip_address = target.ip_cidr.split("/", 1)[0]
    require_host_command(
        context,
        (
            f"sudo qm set {target.target_vmid} "
            f"--name {shlex.quote('restore-verify-' + target.vm_name)} "
            f"--tags {shlex.quote('restore-verification;' + compact_timestamp())} "
            f"--net0 {shlex.quote('virtio=' + target.mac_address + ',bridge=' + target.bridge)} "
            f"--ipconfig0 {shlex.quote('ip=' + target.ip_cidr + ',gw=' + target.gateway)} "
            "--onboot 0"
        ),
        action=f"configure restored VM {target.vm_name}",
    )
    require_host_command(
        context,
        f"sudo qm cloudinit update {target.target_vmid}",
        action=f"refresh cloud-init for {target.vm_name}",
    )
    require_host_command(
        context,
        f"sudo qm start {target.target_vmid}",
        action=f"start restored VM {target.vm_name}",
    )
    context.setdefault("restored_guests", {})[target.vm_name] = ip_address


def load_health_probe_catalog() -> dict[str, Any]:
    payload = load_json(HEALTH_PROBE_CATALOG_PATH)
    return payload.get("services", {})


def load_service_catalog() -> dict[str, Any]:
    payload = load_json(SERVICE_CATALOG_PATH)
    services = payload.get("services", [])
    return {service["id"]: service for service in services}


def docker_runtime_probes() -> list[dict[str, Any]]:
    probes = load_health_probe_catalog()
    return [
        {
            "name": "keycloak_ready",
            "url": probes["keycloak"]["readiness"]["url"],
            "expected_status": probes["keycloak"]["readiness"]["expected_status"][0],
            "required": True,
        },
        {
            "name": "openbao_ready",
            "url": probes["openbao"]["readiness"]["url"],
            "expected_status": probes["openbao"]["readiness"]["expected_status"][0],
            "required": False,
        },
        {
            "name": "netbox_ready",
            "url": probes["netbox"]["readiness"]["url"],
            "expected_status": probes["netbox"]["readiness"]["expected_status"][0],
            "required": True,
        },
        {
            "name": "windmill_ready",
            "url": probes["windmill"]["readiness"]["url"],
            "expected_status": probes["windmill"]["readiness"]["expected_status"][0],
            "required": True,
        },
    ]


def backup_vm_commands() -> list[dict[str, Any]]:
    probes = load_health_probe_catalog()
    readiness = probes["backup_pbs"]["readiness"]
    liveness = probes["backup_pbs"]["liveness"]
    return [
        {
            "name": "backup_pbs_port",
            "command": f"python3 - <<'PY'\nimport socket\nsock = socket.create_connection(({liveness['host']!r}, {int(liveness['port'])}), timeout=10)\nsock.close()\nPY",
            "required": True,
        },
        {
            "name": "backup_pbs_datastore_list",
            "command": " ".join(shlex.quote(part) for part in readiness["argv"]),
            "required": True,
        },
    ]


def execute_smoke_tests(
    context: dict[str, Any],
    target: RestoreTarget,
    *,
    execution_mode: str,
    docker_wait_seconds: int,
) -> list[dict[str, Any]]:
    ip_address = context["restored_guests"][target.vm_name]
    if execution_mode == "ssh":
        command_runner: Callable[[str], CommandOutcome] = lambda command: run_restored_guest_command(
            context, ip_address, command
        )
    elif execution_mode == "qga":
        command_runner = lambda command: run_restored_guest_agent_command(context, target.target_vmid, command)
    else:
        raise ValueError(f"unsupported execution mode: {execution_mode}")

    if target.smoke_kind == "postgres":
        return postgres_smoke.run_smoke_tests(command_runner)
    if target.smoke_kind == "docker-runtime":
        if docker_wait_seconds > 0:
            time.sleep(docker_wait_seconds)
        return docker_runtime_smoke.run_smoke_tests(
            command_runner,
            probes=docker_runtime_probes(),
        )
    if target.smoke_kind == "backup-vm":
        return backup_vm_smoke.run_smoke_tests(
            command_runner,
            commands=backup_vm_commands(),
        )
    raise ValueError(f"unsupported smoke-test kind: {target.smoke_kind}")


def overall_from_tests(tests: list[dict[str, Any]]) -> str:
    required_failures = [
        test for test in tests if test.get("required", True) and test.get("status") != "pass"
    ]
    return "fail" if required_failures else "pass"


def execute_synthetic_replay(
    context: dict[str, Any],
    target: RestoreTarget,
    *,
    execution_mode: str,
) -> dict[str, Any] | None:
    if target.vm_name != "docker-runtime-lv3":
        return None
    ip_address = context["restored_guests"][target.vm_name]
    if execution_mode == "ssh":
        command_runner: Callable[[str], CommandOutcome] = lambda command: run_restored_guest_command(
            context, ip_address, command
        )
    elif execution_mode == "qga":
        command_runner = lambda command: run_restored_guest_agent_command(context, target.target_vmid, command)
    else:
        raise ValueError(f"unsupported execution mode: {execution_mode}")
    report = synthetic_transaction_replay.run_target_profile(
        "restore-docker-runtime",
        execute_command=command_runner,
    )
    report["target_address"] = ip_address
    report["execution_mode"] = execution_mode
    return report


def build_synthetic_replay_test(replay_report: dict[str, Any]) -> dict[str, Any]:
    latency = replay_report.get("latency_ms", {})
    return {
        "name": "synthetic_transaction_replay",
        "status": "pass" if replay_report.get("overall") == "pass" else "fail",
        "required": True,
        "success_rate": replay_report.get("success_rate"),
        "p50_latency_ms": latency.get("p50"),
        "p95_latency_ms": latency.get("p95"),
        "max_latency_ms": latency.get("max"),
        "window": replay_report.get("window_assessment", {}).get("window"),
        "summary": replay_report.get("summary"),
    }


def build_target_result(
    *,
    target: RestoreTarget,
    backup: dict[str, Any],
    restore_duration_seconds: int,
    boot_time_seconds: int,
    execution_mode: str,
    tests: list[dict[str, Any]],
    synthetic_replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    combined_tests = list(tests)
    if synthetic_replay is not None:
        combined_tests.append(build_synthetic_replay_test(synthetic_replay))
    return {
        "vm": target.vm_name,
        "source_vmid": target.source_vmid,
        "target_vmid": target.target_vmid,
        "backup_volid": backup["volid"],
        "backup_date": backup["timestamp"].astimezone(__import__("datetime").timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "restore_ip": target.ip_cidr.split("/", 1)[0],
        "restore_duration_seconds": restore_duration_seconds,
        "boot_time_seconds": boot_time_seconds,
        "execution_mode": execution_mode,
        "smoke_tests": tests,
        "synthetic_replay": synthetic_replay,
        "tests": combined_tests,
        "overall": overall_from_tests(combined_tests),
    }


def build_failure_result(target: RestoreTarget, backup: dict[str, Any] | None, error: str) -> dict[str, Any]:
    return {
        "vm": target.vm_name,
        "source_vmid": target.source_vmid,
        "target_vmid": target.target_vmid,
        "backup_volid": backup["volid"] if backup else "",
        "backup_date": (
            backup["timestamp"].astimezone(__import__("datetime").timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
            if backup
            else ""
        ),
        "tests": [
            {
                "name": "restore_workflow",
                "status": "fail",
                "required": True,
                "error": error,
            }
        ],
        "overall": "fail",
    }


def summarize_report(results: list[dict[str, Any]]) -> tuple[str, str]:
    passed = sum(1 for item in results if item["overall"] == "pass")
    failed = len(results) - passed
    summary = f"{passed}/{len(results)} VMs passed restore verification"
    return summary, "pass" if failed == 0 else "fail"


def latest_success_age_days(receipt_dir: Path, current_report: dict[str, Any]) -> int:
    successful_dates: list[Any] = []
    if current_report.get("overall") == "pass":
        successful_dates.append(utc_now())
    if receipt_dir.exists():
        for path in sorted(receipt_dir.glob("*.json")):
            payload = load_json(path, default={})
            if payload.get("overall") != "pass":
                continue
            run_date = payload.get("run_date")
            if isinstance(run_date, str) and run_date.strip():
                successful_dates.append(
                    __import__("datetime").datetime.fromisoformat(run_date.replace("Z", "+00:00"))
                )
    if not successful_dates:
        return 9999
    latest = max(successful_dates)
    return max(0, int((utc_now() - latest).total_seconds() // 86400))


def maybe_write_metrics(report: dict[str, Any], *, receipt_dir: Path, environment: str) -> None:
    influx_url = os.environ.get("RESTORE_VERIFICATION_INFLUXDB_URL", "").strip()
    influx_bucket = os.environ.get("RESTORE_VERIFICATION_INFLUXDB_BUCKET", "").strip()
    influx_org = os.environ.get("RESTORE_VERIFICATION_INFLUXDB_ORG", "").strip()
    influx_token = os.environ.get("RESTORE_VERIFICATION_INFLUXDB_TOKEN", "").strip()
    if not all((influx_url, influx_bucket, influx_org, influx_token)):
        return

    summary = report["summary"]
    status_code = 0 if report["overall"] == "pass" else 2
    line = (
        f"backup_restore_verification_summary,environment={environment} "
        f"status_code={status_code}i,"
        f"pass_count={summary['pass_count']}i,"
        f"fail_count={summary['fail_count']}i,"
        f"target_count={summary['target_count']}i,"
        f"last_success_age_days={latest_success_age_days(receipt_dir, report)}i"
    )
    request = urllib.request.Request(
        f"{influx_url.rstrip('/')}/api/v2/write?org={urllib.parse.quote(influx_org)}&bucket={urllib.parse.quote(influx_bucket)}&precision=s",
        data=line.encode("utf-8"),
        headers={"Authorization": f"Token {influx_token}", "Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10):
        return


def maybe_publish_nats(report: dict[str, Any], *, publish: bool, context: dict[str, Any]) -> None:
    if not publish:
        return

    base_event = {
        "run_date": report["run_date"],
        "triggered_by": report["triggered_by"],
        "summary": report["summary"]["summary"],
        "overall": report["overall"],
        "results": report["results"],
    }
    events = [
        {
            **base_event,
            "event": "platform.backup.restore-verification.completed",
        }
    ]
    if report["overall"] != "pass":
        events.append(
            {
                **base_event,
                "event": "platform.backup.restore-verification.failed",
            }
        )

    nats_url = os.environ.get("LV3_NATS_URL", "").strip()
    credentials = resolve_nats_credentials(context)
    if nats_url:
        publish_nats_events(events, nats_url=nats_url, credentials=credentials)
        return
    with nats_tunnel(context) as local_port:
        publish_nats_events(
            events,
            nats_url=f"nats://127.0.0.1:{local_port}",
            credentials=credentials,
        )


def build_mattermost_message(report: dict[str, Any], receipt_path: Path) -> str:
    lines = [f"{'OK' if report['overall'] == 'pass' else 'FAIL'} Restore verification completed ({report['run_date'][:10]})"]
    for item in report["results"]:
        backup_date = item.get("backup_date", "")[:10]
        duration = item.get("restore_duration_seconds", 0)
        lines.append(
            f"- {item['vm']}: {item['overall'].upper()} "
            f"(backup {backup_date}, restore {duration}s)"
        )
    lines.append(f"Receipt: {receipt_path}")
    return "\n".join(lines)


def maybe_notify_mattermost(report: dict[str, Any], receipt_path: Path) -> None:
    webhook_url = os.environ.get("RESTORE_VERIFICATION_MATTERMOST_WEBHOOK", "").strip()
    if not webhook_url:
        return
    payload = {"text": build_mattermost_message(report, receipt_path)}
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10):
        return


def emit_mutation_audit(report: dict[str, Any], receipt_path: Path, *, actor_id: str, triggered_by: str) -> None:
    surface = "windmill" if triggered_by.startswith("windmill") else "manual"
    outcome = "success" if report["overall"] == "pass" else "failure"
    event = build_event(
        actor_class="automation",
        actor_id=actor_id,
        surface=surface,
        action="backup.restore_verification",
        target="backup-restore-verification",
        outcome=outcome,
        evidence_ref=str(receipt_path.relative_to(repo_path())),
    )
    emit_event_best_effort(event, context="backup restore verification", stderr=sys.stderr)


def build_report(results: list[dict[str, Any]], *, triggered_by: str, environment: str) -> dict[str, Any]:
    summary_text, overall = summarize_report(results)
    pass_count = sum(1 for item in results if item["overall"] == "pass")
    fail_count = len(results) - pass_count
    return {
        "schema_version": "1.0",
        "run_date": isoformat(utc_now()),
        "environment": environment,
        "triggered_by": triggered_by,
        "results": results,
        "summary": {
            "summary": summary_text,
            "target_count": len(results),
            "pass_count": pass_count,
            "fail_count": fail_count,
        },
        "overall": overall,
    }


def write_receipt(report: dict[str, Any], *, receipt_dir: Path) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    path = receipt_dir / f"{report['run_date'][:10]}.json"
    write_json(path, report, indent=2, sort_keys=True)
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--environment", default="production")
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--selection-strategy", default="random", choices=sorted(ALLOWED_SELECTION_STRATEGIES))
    parser.add_argument(
        "--targets",
        help="Comma-separated target guest names to replay, for example docker-runtime-lv3 or postgres-lv3,docker-runtime-lv3.",
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument("--ssh-timeout-seconds", type=int, default=300)
    parser.add_argument("--docker-wait-seconds", type=int, default=90)
    parser.add_argument("--triggered-by", default="manual")
    parser.add_argument("--actor-id", default="restore-verification")
    parser.add_argument("--publish-nats", action="store_true")
    parser.add_argument("--print-report-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        context = load_controller_context()
        rng = random.Random(args.seed if args.seed is not None else utc_now().toordinal())
        results: list[dict[str, Any]] = []
        selected_names = args.targets.split(",") if args.targets else None

        for target in select_restore_targets(selected_names):
            selected_backup: dict[str, Any] | None = None
            try:
                backups = list_backups_for_vmid(context, target.source_vmid)
                selected_backup = select_backup(
                    backups,
                    lookback_days=args.lookback_days,
                    selection_strategy=args.selection_strategy,
                    rng=rng,
                )
                restore_duration_seconds = restore_backup(context, target, selected_backup)
                configure_restored_vm(context, target)
                execution_mode, boot_time_seconds = wait_for_guest_access(
                    context,
                    target,
                    timeout_seconds=args.ssh_timeout_seconds,
                )
                tests = execute_smoke_tests(
                    context,
                    target,
                    execution_mode=execution_mode,
                    docker_wait_seconds=args.docker_wait_seconds,
                )
                synthetic_replay = execute_synthetic_replay(
                    context,
                    target,
                    execution_mode=execution_mode,
                )
                results.append(
                    build_target_result(
                        target=target,
                        backup=selected_backup,
                        restore_duration_seconds=restore_duration_seconds,
                        boot_time_seconds=boot_time_seconds,
                        execution_mode=execution_mode,
                        tests=tests,
                        synthetic_replay=synthetic_replay,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(build_failure_result(target, selected_backup, str(exc)))
            finally:
                destroy_restored_vm(context, target.target_vmid)

        report = build_report(
            results,
            triggered_by=args.triggered_by,
            environment=args.environment,
        )
        receipt_path = write_receipt(report, receipt_dir=args.receipt_dir)
        maybe_write_metrics(report, receipt_dir=args.receipt_dir, environment=args.environment)
        maybe_publish_nats(report, publish=args.publish_nats, context=context)
        maybe_notify_mattermost(report, receipt_path)
        emit_mutation_audit(
            report,
            receipt_path,
            actor_id=args.actor_id,
            triggered_by=args.triggered_by,
        )

        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        print(f"Receipt: {receipt_path}")
        if args.print_report_json:
            print(f"REPORT_JSON={json.dumps(report, separators=(',', ':'))}")
        return 0 if report["overall"] == "pass" else 1
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("restore verification", exc)


if __name__ == "__main__":
    raise SystemExit(main())
