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
from capacity_report import ResourceAmount, check_capacity_class_request, load_capacity_model
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
import seed_data_snapshots


DEFAULT_RECEIPT_DIR = repo_path("receipts", "restore-verifications")
FIXTURE_DEFINITIONS_DIR = repo_path("tests", "fixtures")
HEALTH_PROBE_CATALOG_PATH = repo_path("config", "health-probe-catalog.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
RESTORE_READINESS_PROFILES_PATH = repo_path("config", "restore-readiness-profiles.json")
STORAGE_ID = "lv3-backup-pbs"
ALLOWED_SELECTION_STRATEGIES = {"latest", "random"}
READINESS_LADDER_STAGES: tuple[tuple[str, str], ...] = (
    ("restore_completed", "restore completed"),
    ("guest_boot_completed", "guest boot completed"),
    ("guest_access_path_ready", "guest access path ready"),
    ("network_and_dependency_path_ready", "network and dependency path ready"),
    ("service_specific_warm_up_completed", "service-specific warm-up completed"),
    ("synthetic_replay_window_passed", "synthetic replay window passed"),
)


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
    resources: ResourceAmount


@dataclass(frozen=True)
class CommandOutcome:
    command: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RestoreReadinessProfile:
    profile_id: str
    service_class: str
    description: str
    initial_wait_seconds: int
    max_attempts: int
    retry_delay_seconds: int
    network_dependency_checks: tuple[str, ...]
    synthetic_replay_enabled: bool
    synthetic_replay_target: str | None = None


@dataclass(frozen=True)
class WarmUpOutcome:
    tests: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    attempts_used: int
    network_dependency_ready_after_attempt: int | None
    service_warm_up_ready_after_attempt: int | None


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
                resources=ResourceAmount(
                    ram_gb=float(fixture["resources"]["memory_mb"]) / 1024.0,
                    vcpu=float(fixture["resources"]["cores"]),
                    disk_gb=float(fixture["resources"]["disk_gb"]),
                ),
            )
        )
    return targets


def load_restore_readiness_profiles() -> dict[str, RestoreReadinessProfile]:
    payload = load_json(RESTORE_READINESS_PROFILES_PATH)
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError("restore-readiness profiles must define an object at config/restore-readiness-profiles.json.profiles")

    loaded: dict[str, RestoreReadinessProfile] = {}
    for profile_id, raw_profile in profiles.items():
        if not isinstance(raw_profile, dict):
            raise ValueError(f"restore-readiness profile '{profile_id}' must be an object")
        synthetic_replay = raw_profile.get("synthetic_replay", {})
        if not isinstance(synthetic_replay, dict):
            raise ValueError(f"restore-readiness profile '{profile_id}'.synthetic_replay must be an object")
        loaded[profile_id] = RestoreReadinessProfile(
            profile_id=str(profile_id),
            service_class=str(raw_profile["service_class"]),
            description=str(raw_profile["description"]),
            initial_wait_seconds=int(raw_profile["initial_wait_seconds"]),
            max_attempts=int(raw_profile["max_attempts"]),
            retry_delay_seconds=int(raw_profile["retry_delay_seconds"]),
            network_dependency_checks=tuple(str(item) for item in raw_profile["network_dependency_checks"]),
            synthetic_replay_enabled=bool(synthetic_replay.get("enabled", False)),
            synthetic_replay_target=(
                str(synthetic_replay["target_id"]).strip()
                if synthetic_replay.get("target_id")
                else None
            ),
        )
    return loaded


def readiness_profile_for_target(
    target: RestoreTarget,
    profiles: dict[str, RestoreReadinessProfile],
) -> RestoreReadinessProfile:
    try:
        return profiles[target.smoke_kind]
    except KeyError as exc:
        raise ValueError(f"no restore-readiness profile declared for smoke kind '{target.smoke_kind}'") from exc


def peak_restore_capacity(targets: list[RestoreTarget]) -> ResourceAmount:
    if not targets:
        return ResourceAmount(ram_gb=0.0, vcpu=0.0, disk_gb=0.0)
    return ResourceAmount(
        ram_gb=max(target.resources.ram_gb for target in targets),
        vcpu=max(target.resources.vcpu for target in targets),
        disk_gb=max(target.resources.disk_gb for target in targets),
    )

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


def build_restored_guest_ssh_base_command(context: dict[str, Any], ip_address: str) -> list[str]:
    return build_restored_guest_ssh_command(context, ip_address, "true")[:-1]


def stage_seed_snapshot(
    context: dict[str, Any],
    target: RestoreTarget,
    *,
    seed_class: str,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    ip_address = target.ip_cidr.split("/", 1)[0]
    stage_root = seed_data_snapshots.guest_stage_root()
    remote_dir = f"{stage_root.rstrip('/')}/restore-verification/{target.vm_name}"
    return seed_data_snapshots.stage_snapshot_to_remote_dir(
        seed_class,
        build_restored_guest_ssh_base_command(context, ip_address),
        remote_dir=remote_dir,
        snapshot_name=snapshot_id,
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


def initialize_readiness_ladder(profile: RestoreReadinessProfile) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    for stage_id, label in READINESS_LADDER_STAGES:
        stage = {
            "id": stage_id,
            "label": label,
            "required": True,
            "status": "pending",
        }
        if stage_id == "synthetic_replay_window_passed" and not profile.synthetic_replay_enabled:
            stage["required"] = False
            stage["status"] = "not_applicable"
            stage["detail"] = "The restore-readiness profile does not declare synthetic replay for this service class."
        stages.append(stage)
    return stages


def update_readiness_ladder_stage(
    ladder: list[dict[str, Any]],
    stage_id: str,
    status: str,
    *,
    detail: str,
    observed: dict[str, Any] | None = None,
) -> None:
    for stage in ladder:
        if stage["id"] != stage_id:
            continue
        stage["status"] = status
        stage["detail"] = detail
        if observed:
            stage["observed"] = observed
        return
    raise KeyError(f"unknown readiness ladder stage '{stage_id}'")


def highest_completed_ladder_stage(ladder: list[dict[str, Any]]) -> dict[str, Any] | None:
    completed: dict[str, Any] | None = None
    for stage in ladder:
        if stage.get("status") == "pass":
            completed = {"id": stage["id"], "label": stage["label"]}
    return completed


def build_readiness_ladder_payload(ladder: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "highest_completed_stage": highest_completed_ladder_stage(ladder),
        "stages": ladder,
    }


def build_readiness_profile_payload(
    profile: RestoreReadinessProfile,
    *,
    warm_up_outcome: WarmUpOutcome | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": profile.profile_id,
        "service_class": profile.service_class,
        "description": profile.description,
        "initial_wait_seconds": profile.initial_wait_seconds,
        "max_attempts": profile.max_attempts,
        "retry_delay_seconds": profile.retry_delay_seconds,
        "network_dependency_checks": list(profile.network_dependency_checks),
        "synthetic_replay": {
            "enabled": profile.synthetic_replay_enabled,
            "target_id": profile.synthetic_replay_target,
        },
    }
    if warm_up_outcome is not None:
        payload["attempts_used"] = warm_up_outcome.attempts_used
        payload["network_dependency_ready_after_attempt"] = (
            warm_up_outcome.network_dependency_ready_after_attempt
        )
        payload["service_warm_up_ready_after_attempt"] = (
            warm_up_outcome.service_warm_up_ready_after_attempt
        )
    return payload


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


def tests_pass_named(tests: list[dict[str, Any]], names: tuple[str, ...]) -> bool:
    if not names:
        return True
    statuses = {str(test["name"]): str(test.get("status", "")) for test in tests}
    return all(statuses.get(name) == "pass" for name in names)


def failing_test_names(
    tests: list[dict[str, Any]],
    *,
    selected_names: tuple[str, ...] | None = None,
    required_only: bool = False,
) -> list[str]:
    selected = set(selected_names or ())
    failed: list[str] = []
    for test in tests:
        name = str(test.get("name", ""))
        if selected and name not in selected:
            continue
        if required_only and not bool(test.get("required", True)):
            continue
        if test.get("status") != "pass":
            failed.append(name)
    return failed


def attempt_elapsed_seconds(attempts: list[dict[str, Any]], attempt_number: int | None) -> int | None:
    if attempt_number is None:
        return None
    for attempt in attempts:
        if int(attempt.get("attempt", 0)) == attempt_number:
            return int(attempt.get("elapsed_seconds", 0))
    return None


def execute_profiled_smoke_tests(
    context: dict[str, Any],
    target: RestoreTarget,
    *,
    execution_mode: str,
    profile: RestoreReadinessProfile,
    docker_wait_seconds: int,
) -> WarmUpOutcome:
    initial_wait_seconds = profile.initial_wait_seconds
    if target.smoke_kind == "docker-runtime":
        initial_wait_seconds = max(initial_wait_seconds, docker_wait_seconds)
    if initial_wait_seconds > 0:
        time.sleep(initial_wait_seconds)

    attempts: list[dict[str, Any]] = []
    latest_tests: list[dict[str, Any]] = []
    network_dependency_ready_after_attempt: int | None = None
    service_warm_up_ready_after_attempt: int | None = None
    started = time.monotonic()

    for attempt in range(1, profile.max_attempts + 1):
        latest_tests = execute_smoke_tests(
            context,
            target,
            execution_mode=execution_mode,
        )
        network_dependency_ready = tests_pass_named(latest_tests, profile.network_dependency_checks)
        service_warm_up_ready = overall_from_tests(latest_tests) == "pass"
        attempts.append(
            {
                "attempt": attempt,
                "elapsed_seconds": int(time.monotonic() - started),
                "network_dependency_path_ready": network_dependency_ready,
                "service_specific_warm_up_completed": service_warm_up_ready,
                "test_statuses": {
                    str(test["name"]): str(test.get("status", "unknown")) for test in latest_tests
                },
            }
        )
        if network_dependency_ready and network_dependency_ready_after_attempt is None:
            network_dependency_ready_after_attempt = attempt
        if service_warm_up_ready:
            service_warm_up_ready_after_attempt = attempt
            break
        if attempt < profile.max_attempts and profile.retry_delay_seconds > 0:
            time.sleep(profile.retry_delay_seconds)

    return WarmUpOutcome(
        tests=latest_tests,
        attempts=attempts,
        attempts_used=len(attempts),
        network_dependency_ready_after_attempt=network_dependency_ready_after_attempt,
        service_warm_up_ready_after_attempt=service_warm_up_ready_after_attempt,
    )


def execute_synthetic_replay(
    context: dict[str, Any],
    target: RestoreTarget,
    *,
    execution_mode: str,
    profile: RestoreReadinessProfile,
) -> dict[str, Any] | None:
    if not profile.synthetic_replay_enabled or not profile.synthetic_replay_target:
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
        profile.synthetic_replay_target,
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
    profile: RestoreReadinessProfile,
    restore_duration_seconds: int,
    boot_time_seconds: int,
    execution_mode: str,
    tests: list[dict[str, Any]],
    readiness_ladder: dict[str, Any],
    warm_up_attempts: list[dict[str, Any]],
    synthetic_replay: dict[str, Any] | None = None,
    warm_up_outcome: WarmUpOutcome | None = None,
    seed_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    combined_tests = list(tests)
    if synthetic_replay is not None:
        combined_tests.append(build_synthetic_replay_test(synthetic_replay))
    payload = {
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
        "readiness_profile": build_readiness_profile_payload(profile, warm_up_outcome=warm_up_outcome),
        "readiness_ladder": readiness_ladder,
        "warm_up_attempts": warm_up_attempts,
        "smoke_tests": tests,
        "synthetic_replay": synthetic_replay,
        "tests": combined_tests,
        "overall": overall_from_tests(combined_tests),
    }
    if seed_snapshot:
        payload["seed_class"] = seed_snapshot["seed_class"]
        payload["seed_snapshot_id"] = seed_snapshot["snapshot_id"]
        payload["seed_snapshot_remote_dir"] = seed_snapshot["remote_dir"]
    return payload


def build_failure_result(
    target: RestoreTarget,
    backup: dict[str, Any] | None,
    error: str,
    *,
    profile: RestoreReadinessProfile | None = None,
    readiness_ladder: dict[str, Any] | None = None,
    warm_up_attempts: list[dict[str, Any]] | None = None,
    tests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    smoke_tests = list(tests or [])
    combined_tests = list(smoke_tests)
    combined_tests.append(
        {
            "name": "restore_workflow",
            "status": "fail",
            "required": True,
            "error": error,
        }
    )
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
        "readiness_profile": build_readiness_profile_payload(profile) if profile is not None else None,
        "readiness_ladder": readiness_ladder,
        "warm_up_attempts": list(warm_up_attempts or []),
        "smoke_tests": smoke_tests,
        "tests": combined_tests,
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
        highest_stage = (
            (((item.get("readiness_ladder") or {}).get("highest_completed_stage") or {}).get("label"))
            or "none"
        )
        lines.append(
            f"- {item['vm']}: {item['overall'].upper()} "
            f"(backup {backup_date}, restore {duration}s, highest stage: {highest_stage})"
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
    try:
        evidence_ref = str(receipt_path.relative_to(repo_path()))
    except ValueError:
        evidence_ref = str(receipt_path)
    event = build_event(
        actor_class="automation",
        actor_id=actor_id,
        surface=surface,
        action="backup.restore_verification",
        target="backup-restore-verification",
        outcome=outcome,
        evidence_ref=evidence_ref,
    )
    emit_event_best_effort(event, context="backup restore verification", stderr=sys.stderr)


def build_report(results: list[dict[str, Any]], *, triggered_by: str, environment: str) -> dict[str, Any]:
    summary_text, overall = summarize_report(results)
    pass_count = sum(1 for item in results if item["overall"] == "pass")
    fail_count = len(results) - pass_count
    highest_stage_counts: dict[str, int] = {}
    for item in results:
        highest_stage = (((item.get("readiness_ladder") or {}).get("highest_completed_stage") or {}).get("id"))
        if not highest_stage:
            highest_stage = "not_started"
        highest_stage_counts[highest_stage] = highest_stage_counts.get(highest_stage, 0) + 1
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
            "highest_completed_stage_counts": highest_stage_counts,
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
    parser.add_argument("--seed-class", choices=seed_data_snapshots.seed_classes())
    parser.add_argument("--seed-snapshot-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        context = load_controller_context()
        profiles = load_restore_readiness_profiles()
        rng = random.Random(args.seed if args.seed is not None else utc_now().toordinal())
        results: list[dict[str, Any]] = []
        selected_names = args.targets.split(",") if args.targets else None
        targets = select_restore_targets(selected_names)
        capacity_verdict = check_capacity_class_request(
            load_capacity_model(),
            requester_class="restore-verification",
            requested=peak_restore_capacity(targets),
            declared_drill=True,
        )
        if not capacity_verdict["approved"]:
            raise RuntimeError(
                "restore verification capacity admission rejected: "
                + "; ".join(capacity_verdict["reasons"])
            )
        for target in targets:
            profile = readiness_profile_for_target(target, profiles)
            ladder = initialize_readiness_ladder(profile)
            selected_backup: dict[str, Any] | None = None
            boot_time_seconds = 0
            execution_mode = "unknown"
            latest_tests: list[dict[str, Any]] = []
            warm_up_outcome: WarmUpOutcome | None = None
            try:
                backups = list_backups_for_vmid(context, target.source_vmid)
                selected_backup = select_backup(
                    backups,
                    lookback_days=args.lookback_days,
                    selection_strategy=args.selection_strategy,
                    rng=rng,
                )
                restore_duration_seconds = restore_backup(context, target, selected_backup)
                update_readiness_ladder_stage(
                    ladder,
                    "restore_completed",
                    "pass",
                    detail=f"Restored {target.vm_name} from {selected_backup['volid']} in {restore_duration_seconds}s.",
                    observed={"restore_duration_seconds": restore_duration_seconds},
                )
                configure_restored_vm(context, target)
                execution_mode, boot_time_seconds = wait_for_guest_access(
                    context,
                    target,
                    timeout_seconds=args.ssh_timeout_seconds,
                )
                update_readiness_ladder_stage(
                    ladder,
                    "guest_boot_completed",
                    "pass",
                    detail=f"The restored guest exposed a usable boot signal after {boot_time_seconds}s.",
                    observed={"boot_time_seconds": boot_time_seconds},
                )
                update_readiness_ladder_stage(
                    ladder,
                    "guest_access_path_ready",
                    "pass",
                    detail=f"The restore workflow reached the guest over the {execution_mode} access path.",
                    observed={
                        "boot_time_seconds": boot_time_seconds,
                        "execution_mode": execution_mode,
                    },
                )
                staged_seed = None
                if args.seed_class:
                    staged_seed = stage_seed_snapshot(
                        context,
                        target,
                        seed_class=args.seed_class,
                        snapshot_id=args.seed_snapshot_id,
                    )
                warm_up_outcome = execute_profiled_smoke_tests(
                    context,
                    target,
                    execution_mode=execution_mode,
                    profile=profile,
                    docker_wait_seconds=args.docker_wait_seconds,
                )
                latest_tests = warm_up_outcome.tests
                if warm_up_outcome.network_dependency_ready_after_attempt is not None:
                    update_readiness_ladder_stage(
                        ladder,
                        "network_and_dependency_path_ready",
                        "pass",
                        detail=(
                            "The profile's dependency checks passed on attempt "
                            f"{warm_up_outcome.network_dependency_ready_after_attempt}."
                        ),
                        observed={
                            "attempt": warm_up_outcome.network_dependency_ready_after_attempt,
                            "elapsed_seconds": attempt_elapsed_seconds(
                                warm_up_outcome.attempts,
                                warm_up_outcome.network_dependency_ready_after_attempt,
                            ),
                        },
                    )
                else:
                    dependency_failures = failing_test_names(
                        latest_tests,
                        selected_names=profile.network_dependency_checks,
                    )
                    update_readiness_ladder_stage(
                        ladder,
                        "network_and_dependency_path_ready",
                        "fail",
                        detail=(
                            "The profile's dependency checks never all passed after "
                            f"{warm_up_outcome.attempts_used} attempts: {', '.join(dependency_failures) or 'unknown'}."
                        ),
                    )
                    update_readiness_ladder_stage(
                        ladder,
                        "service_specific_warm_up_completed",
                        "skipped",
                        detail="Skipped because the network and dependency path never reached readiness.",
                    )
                    if profile.synthetic_replay_enabled:
                        update_readiness_ladder_stage(
                            ladder,
                            "synthetic_replay_window_passed",
                            "skipped",
                            detail="Skipped because the service-specific warm-up stage never became eligible.",
                        )

                synthetic_replay: dict[str, Any] | None = None
                if warm_up_outcome.network_dependency_ready_after_attempt is not None:
                    if warm_up_outcome.service_warm_up_ready_after_attempt is not None:
                        update_readiness_ladder_stage(
                            ladder,
                            "service_specific_warm_up_completed",
                            "pass",
                            detail=(
                                "All required warm-up checks passed on attempt "
                                f"{warm_up_outcome.service_warm_up_ready_after_attempt}."
                            ),
                            observed={
                                "attempt": warm_up_outcome.service_warm_up_ready_after_attempt,
                                "elapsed_seconds": attempt_elapsed_seconds(
                                    warm_up_outcome.attempts,
                                    warm_up_outcome.service_warm_up_ready_after_attempt,
                                ),
                            },
                        )
                        if profile.synthetic_replay_enabled:
                            try:
                                synthetic_replay = execute_synthetic_replay(
                                    context,
                                    target,
                                    execution_mode=execution_mode,
                                    profile=profile,
                                )
                            except Exception as exc:  # noqa: BLE001
                                synthetic_replay = {
                                    "overall": "fail",
                                    "summary": str(exc),
                                    "target_id": profile.synthetic_replay_target,
                                }

                            if synthetic_replay and synthetic_replay.get("overall") == "pass":
                                update_readiness_ladder_stage(
                                    ladder,
                                    "synthetic_replay_window_passed",
                                    "pass",
                                    detail=synthetic_replay.get("summary", "Synthetic replay passed."),
                                    observed={
                                        "target_id": synthetic_replay.get("target_id") or profile.synthetic_replay_target,
                                        "execution_mode": synthetic_replay.get("execution_mode", execution_mode),
                                    },
                                )
                            else:
                                update_readiness_ladder_stage(
                                    ladder,
                                    "synthetic_replay_window_passed",
                                    "fail",
                                    detail=(
                                        (synthetic_replay or {}).get("summary")
                                        or "Synthetic replay failed after the warm-up window."
                                    ),
                                    observed={
                                        "target_id": profile.synthetic_replay_target,
                                        "execution_mode": execution_mode,
                                    },
                                )
                    else:
                        required_failures = failing_test_names(latest_tests, required_only=True)
                        update_readiness_ladder_stage(
                            ladder,
                            "service_specific_warm_up_completed",
                            "fail",
                            detail=(
                                "Required warm-up checks still failed after "
                                f"{warm_up_outcome.attempts_used} attempts: {', '.join(required_failures) or 'unknown'}."
                            ),
                        )
                        if profile.synthetic_replay_enabled:
                            update_readiness_ladder_stage(
                                ladder,
                                "synthetic_replay_window_passed",
                                "skipped",
                                detail="Skipped because the service-specific warm-up stage never passed.",
                            )

                results.append(
                    build_target_result(
                        target=target,
                        backup=selected_backup,
                        profile=profile,
                        restore_duration_seconds=restore_duration_seconds,
                        boot_time_seconds=boot_time_seconds,
                        execution_mode=execution_mode,
                        tests=latest_tests,
                        readiness_ladder=build_readiness_ladder_payload(ladder),
                        warm_up_attempts=warm_up_outcome.attempts if warm_up_outcome is not None else [],
                        synthetic_replay=synthetic_replay,
                        warm_up_outcome=warm_up_outcome,
                        seed_snapshot=staged_seed,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                current_stage_id = next(
                    (
                        stage["id"]
                        for stage in ladder
                        if stage.get("required", True) and stage.get("status") == "pending"
                    ),
                    "restore_completed",
                )
                update_readiness_ladder_stage(
                    ladder,
                    current_stage_id,
                    "fail",
                    detail=str(exc),
                )
                if profile.synthetic_replay_enabled:
                    synthetic_stage = next(
                        (stage for stage in ladder if stage["id"] == "synthetic_replay_window_passed"),
                        None,
                    )
                    if synthetic_stage is not None and synthetic_stage.get("status") == "pending":
                        update_readiness_ladder_stage(
                            ladder,
                            "synthetic_replay_window_passed",
                            "skipped",
                            detail="Skipped because an earlier required restore stage failed.",
                        )
                results.append(
                    build_failure_result(
                        target,
                        selected_backup,
                        str(exc),
                        profile=profile,
                        readiness_ladder=build_readiness_ladder_payload(ladder),
                        warm_up_attempts=warm_up_outcome.attempts if warm_up_outcome is not None else [],
                        tests=latest_tests,
                    )
                )
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
