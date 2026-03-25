#!/usr/bin/env python3

import argparse
import base64
import concurrent.futures
import json
import math
import os
import re
import shlex
import socket
import ssl
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path, write_json
from maintenance_window_tool import list_active_windows_best_effort, suppress_findings_for_maintenance
from platform.events import build_envelope
from tls_cert_probe import collect_certificate_results


HEALTH_PROBE_CATALOG_PATH = repo_path("config", "health-probe-catalog.json")
SECRET_CATALOG_PATH = repo_path("config", "secret-catalog.json")
IMAGE_CATALOG_PATH = repo_path("config", "image-catalog.json")
FINDING_SCHEMA_PATH = repo_path("docs", "schema", "platform-finding.json")
HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
GROUP_VARS_PATH = repo_path("inventory", "group_vars", "all.yml")
SECRET_MANIFEST_PATH = repo_path("config", "controller-local-secrets.json")
DEFAULT_OUTPUT_DIR = repo_path(".local", "platform-observation", "latest")
DEFAULT_DIGEST_PATH = repo_path(".local", "open-webui", "platform-findings-daily.md")


RUNNER_VALUES = {"controller_local", "host_ssh", "guest_jump"}
SEVERITY_VALUES = {"ok", "warning", "critical", "suppressed"}


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def truncate(value: str, limit: int = 400) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def normalize_image_reference(reference: str) -> str:
    normalized = reference.strip()
    for prefix in ("docker.io/", "index.docker.io/"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
            break
    if normalized.startswith("library/"):
        normalized = normalized.removeprefix("library/")
    return normalized


def iter_observation_images(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    images = catalog["images"]
    if isinstance(images, list):
        return images
    if not isinstance(images, dict):
        raise ValueError("config/image-catalog.json.images must be a list or object")

    normalized: list[dict[str, Any]] = []
    for image_id, image in sorted(images.items()):
        if image.get("kind") != "runtime":
            continue
        runtime_host = image.get("runtime_host")
        container_name = image.get("container_name")
        if not runtime_host or not container_name:
            continue
        normalized.append(
            {
                "id": image_id,
                "service_id": image.get("service_id", image_id),
                "runtime_host": runtime_host,
                "container_name": container_name,
                "image_reference": image["ref"],
                "source_kind": "upstream",
                "pin_status": "pinned",
                "pinned_digest": image["digest"],
            }
        )
    return normalized


def load_observation_context() -> dict[str, Any]:
    host_vars = load_yaml(HOST_VARS_PATH)
    group_vars = load_yaml(GROUP_VARS_PATH)
    secret_manifest = load_json(SECRET_MANIFEST_PATH)
    bootstrap_key = Path(secret_manifest["secrets"]["bootstrap_ssh_private_key"]["path"]).expanduser()

    guests = {
        guest["name"]: guest["ipv4"]
        for guest in host_vars["proxmox_guests"]
    }
    return {
        "host_vars": host_vars,
        "group_vars": group_vars,
        "secret_manifest": secret_manifest,
        "bootstrap_key": bootstrap_key,
        "host_user": group_vars["proxmox_host_admin_user"],
        "host_addr": host_vars["management_tailscale_ipv4"],
        "guests": guests,
    }


def run_subprocess(command: list[str]) -> CommandResult:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return CommandResult(
        command=" ".join(shlex.quote(part) for part in command),
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def run_shell(command: str) -> CommandResult:
    return run_subprocess(["/bin/bash", "-lc", command])


def build_host_ssh_command(context: dict[str, Any], remote_command: str) -> list[str]:
    key_path = str(context["bootstrap_key"])
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
        f"{context['host_user']}@{context['host_addr']}",
        remote_command,
    ]


def build_guest_ssh_command(context: dict[str, Any], target: str, remote_command: str) -> list[str]:
    key_path = str(context["bootstrap_key"])
    guest_ip = context["guests"][target]
    proxy_command = (
        f"ssh -i {shlex.quote(key_path)} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 -o LogLevel=ERROR "
        f"{shlex.quote(f'{context['host_user']}@{context['host_addr']}')} -W %h:%p"
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
        f"{context['host_user']}@{guest_ip}",
        remote_command,
    ]


def execute_runner(context: dict[str, Any], runner: str, target: str, command: str) -> CommandResult:
    if runner == "controller_local":
        return run_shell(command)
    if runner == "host_ssh":
        return run_subprocess(build_host_ssh_command(context, command))
    if runner == "guest_jump":
        return run_subprocess(build_guest_ssh_command(context, target, command))
    raise ValueError(f"Unsupported runner: {runner}")


def validate_finding_schema(finding: dict[str, Any]) -> None:
    schema = load_json(FINDING_SCHEMA_PATH)
    required = schema["required"]
    for key in required:
        if key not in finding:
            raise ValueError(f"finding is missing required key '{key}'")
    if finding["severity"] not in SEVERITY_VALUES:
        raise ValueError(f"invalid finding severity '{finding['severity']}'")
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", finding["check"]):
        raise ValueError(f"invalid finding check id '{finding['check']}'")


def make_finding(
    *,
    check: str,
    severity: str,
    summary: str,
    details: list[dict[str, Any]],
    run_id: str,
    outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "check": check,
        "severity": severity,
        "summary": summary,
        "details": details,
        "ts": isoformat(utc_now()),
        "run_id": run_id,
    }
    if outputs:
        finding["outputs"] = outputs
    validate_finding_schema(finding)
    return finding


def evaluate_probe_result(probe: dict[str, Any], result: CommandResult) -> tuple[bool, dict[str, Any]]:
    expect = probe["expect"]
    ok = result.returncode == expect.get("exit_code", 0)
    stdout = result.stdout
    stderr = result.stderr

    if "stdout_contains" in expect:
        for fragment in expect["stdout_contains"]:
            if fragment not in stdout:
                ok = False
    if "stdout_regex" in expect and not re.search(expect["stdout_regex"], stdout, re.MULTILINE):
        ok = False

    detail = {
        "probe_id": probe["id"],
        "service_id": probe["service_id"],
        "runner": probe["runner"],
        "target": probe["target"],
        "command": result.command,
        "returncode": result.returncode,
        "stdout": truncate(stdout),
        "stderr": truncate(stderr),
        "ok": ok,
    }
    return ok, detail


def build_probe_execution_context(target: str) -> tuple[str, str]:
    if target == "proxmox_florin":
        return "host_ssh", "proxmox_florin"
    return "guest_jump", target


def join_argv(argv: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)


def build_http_probe_command(probe_definition: dict[str, Any]) -> str:
    parts = [
        "curl",
        "-sS",
        "--max-time",
        str(probe_definition["timeout_seconds"]),
        "-X",
        probe_definition["method"],
    ]
    if not probe_definition.get("validate_tls", True):
        parts.append("-k")
    for key, value in probe_definition.get("headers", {}).items():
        parts.extend(["-H", f"{key}: {value}"])
    parts.extend([probe_definition["url"], "-w", "\\n__STATUS__=%{http_code}"])
    return join_argv(parts)


def build_tcp_probe_command(probe_definition: dict[str, Any]) -> str:
    return (
        "python3 - <<'PY'\n"
        "import socket\n"
        f"host = {probe_definition['host']!r}\n"
        f"port = {probe_definition['port']!r}\n"
        f"timeout = {probe_definition['timeout_seconds']!r}\n"
        "with socket.create_connection((host, port), timeout=timeout):\n"
        "    print('connected')\n"
        "PY"
    )


def parse_http_probe_output(stdout: str) -> tuple[str, int | None]:
    marker = "\n__STATUS__="
    if marker not in stdout:
        return stdout, None
    body, _, status_text = stdout.rpartition(marker)
    try:
        return body, int(status_text.strip())
    except ValueError:
        return body, None


def build_service_probes(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    if "probes" in catalog:
        return catalog["probes"]
    probes: list[dict[str, Any]] = []
    for service_id, service in sorted(catalog["services"].items()):
        for phase in ("liveness", "readiness"):
            probes.append(
                {
                    "id": f"{service_id}-{phase}",
                    "service_id": service_id,
                    "runner": "structured",
                    "target": service["owning_vm"],
                    "phase": phase,
                    "definition": service[phase],
                }
            )
    return probes


def execute_structured_probe(context: dict[str, Any], probe: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    probe_definition = probe["definition"]
    runner, target = build_probe_execution_context(probe["target"])
    kind = probe_definition["kind"]

    if kind == "systemd":
        command = f"systemctl is-active {shlex.quote(probe_definition['unit'])}"
        result = execute_runner(context, runner, target, command)
        ok = result.returncode == 0 and result.stdout.strip() == probe_definition["expected_state"]
        detail = {
            "probe_id": probe["id"],
            "service_id": probe["service_id"],
            "probe_phase": probe["phase"],
            "probe_kind": kind,
            "runner": runner,
            "target": target,
            "command": result.command,
            "returncode": result.returncode,
            "stdout": truncate(result.stdout),
            "stderr": truncate(result.stderr),
            "ok": ok,
        }
        return ok, detail

    if kind == "command":
        command = join_argv(probe_definition["argv"])
        result = execute_runner(context, runner, target, command)
        ok = result.returncode == probe_definition.get("success_rc", 0)
        detail = {
            "probe_id": probe["id"],
            "service_id": probe["service_id"],
            "probe_phase": probe["phase"],
            "probe_kind": kind,
            "runner": runner,
            "target": target,
            "command": result.command,
            "returncode": result.returncode,
            "stdout": truncate(result.stdout),
            "stderr": truncate(result.stderr),
            "ok": ok,
        }
        return ok, detail

    if kind == "http":
        command = build_http_probe_command(probe_definition)
        result = execute_runner(context, runner, target, command)
        body, status_code = parse_http_probe_output(result.stdout)
        ok = result.returncode == 0 and status_code in probe_definition["expected_status"]
        detail = {
            "probe_id": probe["id"],
            "service_id": probe["service_id"],
            "probe_phase": probe["phase"],
            "probe_kind": kind,
            "runner": runner,
            "target": target,
            "command": result.command,
            "returncode": result.returncode,
            "http_status": status_code,
            "stdout": truncate(body),
            "stderr": truncate(result.stderr),
            "ok": ok,
        }
        return ok, detail

    if kind == "tcp":
        command = build_tcp_probe_command(probe_definition)
        result = execute_runner(context, runner, target, command)
        ok = result.returncode == 0
        detail = {
            "probe_id": probe["id"],
            "service_id": probe["service_id"],
            "probe_phase": probe["phase"],
            "probe_kind": kind,
            "runner": runner,
            "target": target,
            "command": result.command,
            "returncode": result.returncode,
            "stdout": truncate(result.stdout),
            "stderr": truncate(result.stderr),
            "ok": ok,
        }
        return ok, detail

    raise ValueError(f"Unsupported structured probe kind: {kind}")


def format_certificate_subject(subject: Any) -> str | None:
    if not subject:
        return None
    parts: list[str] = []
    for relative_name in subject:
        for key, value in relative_name:
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else None


def decode_binary_certificate(binary_certificate: bytes) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", delete=False) as handle:
        handle.write(ssl.DER_cert_to_PEM_cert(binary_certificate))
        temp_path = handle.name
    try:
        return ssl._ssl._test_decode_cert(temp_path)
    finally:
        os.unlink(temp_path)


def probe_tls_certificate(
    host: str,
    port: int,
    *,
    server_name: str | None = None,
    timeout_seconds: int = 10,
) -> tuple[str | None, datetime]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with socket.create_connection((host, port), timeout=timeout_seconds) as tcp_socket:
        with context.wrap_socket(tcp_socket, server_hostname=server_name or host) as tls_socket:
            certificate = tls_socket.getpeercert()
            if not certificate:
                binary_certificate = tls_socket.getpeercert(binary_form=True)
                if not binary_certificate:
                    raise RuntimeError(f"Peer certificate was empty for {host}:{port}")
                certificate = decode_binary_certificate(binary_certificate)

    not_after = certificate.get("notAfter")
    if not not_after:
        raise RuntimeError(f"Peer certificate did not include notAfter for {host}:{port}")
    expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    return format_certificate_subject(certificate.get("subject")), expires


def check_service_health(context: dict[str, Any], run_id: str) -> dict[str, Any]:
    catalog = load_json(HEALTH_PROBE_CATALOG_PATH)
    probes = build_service_probes(catalog)
    failures: list[dict[str, Any]] = []
    successes: list[dict[str, Any]] = []

    def run_probe(probe: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        if probe.get("runner") == "structured":
            return execute_structured_probe(context, probe)
        result = execute_runner(context, probe["runner"], probe["target"], probe["command"])
        return evaluate_probe_result(probe, result)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(run_probe, probe) for probe in probes]
        for future in concurrent.futures.as_completed(futures):
            ok, detail = future.result()
            if ok:
                successes.append(detail)
            else:
                failures.append(detail)
    failures.sort(key=lambda item: item["probe_id"])
    successes.sort(key=lambda item: item["probe_id"])

    if failures:
        severity = "critical"
        summary = f"{len(failures)} of {len(probes)} service probes failed."
    else:
        severity = "ok"
        summary = f"All {len(probes)} service probes passed."
    return make_finding(
        check="check-service-health",
        severity=severity,
        summary=summary,
        details=failures or successes,
        run_id=run_id,
        outputs={"checked_probe_count": len(probes)},
    )


def check_vm_state(context: dict[str, Any], run_id: str) -> dict[str, Any]:
    desired_guests = {
        guest["vmid"]: guest["name"]
        for guest in context["host_vars"]["proxmox_guests"]
    }
    result = execute_runner(
        context,
        "host_ssh",
        "proxmox_florin",
        "sudo pvesh get /nodes/$(hostname)/qemu --output-format json",
    )
    if result.returncode != 0:
        return make_finding(
            check="check-vm-state",
            severity="critical",
            summary="Unable to read Proxmox VM state from the host.",
            details=[
                {
                    "command": result.command,
                    "returncode": result.returncode,
                    "stdout": truncate(result.stdout),
                    "stderr": truncate(result.stderr),
                }
            ],
            run_id=run_id,
        )

    live_guests = {entry["vmid"]: entry for entry in json.loads(result.stdout)}
    details: list[dict[str, Any]] = []

    for vmid, name in desired_guests.items():
        guest = live_guests.get(vmid)
        if guest is None:
            details.append({"vmid": vmid, "name": name, "status": "missing"})
            continue
        if guest.get("name") != name or guest.get("status") != "running":
            details.append(
                {
                    "vmid": vmid,
                    "expected_name": name,
                    "actual_name": guest.get("name"),
                    "status": guest.get("status"),
                }
            )

    severity = "ok" if not details else "critical"
    summary = "All managed guests are running with the expected identity." if not details else (
        f"{len(details)} guest state mismatches detected."
    )
    return make_finding(
        check="check-vm-state",
        severity=severity,
        summary=summary,
        details=details or [{"managed_guest_count": len(desired_guests)}],
        run_id=run_id,
    )


def check_image_freshness(context: dict[str, Any], run_id: str) -> dict[str, Any]:
    catalog = load_json(IMAGE_CATALOG_PATH)
    images = iter_observation_images(catalog)
    details: list[dict[str, Any]] = []
    severity_rank = {"ok": 0, "warning": 1, "critical": 2}
    severity = "ok"

    def inspect_image(image: dict[str, Any]) -> tuple[dict[str, Any], CommandResult]:
        inspect_command = (
            "docker inspect --format '{{.Config.Image}}|{{.Image}}' "
            + shlex.quote(image["container_name"])
        )
        return image, execute_runner(context, "guest_jump", image["runtime_host"], inspect_command)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(inspect_image, image) for image in images]
        for future in concurrent.futures.as_completed(futures):
            image, result = future.result()
            if result.returncode != 0:
                details.append(
                    {
                        "image_id": image["id"],
                        "container_name": image["container_name"],
                        "status": "missing_container",
                        "stderr": truncate(result.stderr),
                    }
                )
                severity = "critical"
                continue

            running_reference, _, running_digest = result.stdout.partition("|")
            entry = {
                "image_id": image["id"],
                "service_id": image["service_id"],
                "container_name": image["container_name"],
                "expected_reference": image["image_reference"],
                "running_reference": running_reference,
                "running_digest": running_digest,
                "pin_status": image["pin_status"],
            }

            if normalize_image_reference(running_reference) != normalize_image_reference(image["image_reference"]):
                entry["status"] = "reference_mismatch"
                details.append(entry)
                severity = "critical"
                continue

            if image["source_kind"] == "local_build":
                entry["status"] = "local_build_ok"
                details.append(entry)
                continue

            if image["pin_status"] != "pinned" or not image.get("pinned_digest"):
                entry["status"] = "unpinned"
                details.append(entry)
                if severity_rank[severity] < severity_rank["warning"]:
                    severity = "warning"
                continue

            if image["pinned_digest"] not in running_reference and image["pinned_digest"] != running_digest:
                entry["status"] = "digest_mismatch"
                details.append(entry)
                severity = "critical"
                continue

            entry["status"] = "pinned_ok"
            details.append(entry)
    details.sort(key=lambda item: item["image_id"])

    summary = "All managed container references match the catalog and are digest-pinned."
    if severity == "warning":
        summary = "Managed containers match the catalog, but one or more images are not digest-pinned."
    elif severity == "critical":
        summary = "One or more managed container images are missing, mismatched, or drifted from the catalog."

    return make_finding(
        check="check-image-freshness",
        severity=severity,
        summary=summary,
        details=details,
        run_id=run_id,
        outputs={"checked_image_count": len(images)},
    )


def check_secret_ages(context: dict[str, Any], run_id: str) -> dict[str, Any]:
    catalog = load_json(SECRET_CATALOG_PATH)
    secret_manifest = context["secret_manifest"]["secrets"]
    now = utc_now()
    details: list[dict[str, Any]] = []
    severity_rank = {"ok": 0, "warning": 1, "critical": 2}
    severity = "ok"

    for secret in catalog["secrets"]:
        manifest_entry = secret_manifest.get(secret["storage_ref"])
        days_since_rotation = (now - parse_date(secret["last_rotated_at"])).days
        days_remaining = secret["rotation_period_days"] - days_since_rotation
        detail = {
            "secret_id": secret["id"],
            "owner_service": secret["owner_service"],
            "storage_ref": secret["storage_ref"],
            "days_since_rotation": days_since_rotation,
            "days_remaining": days_remaining,
        }

        if manifest_entry is None:
            detail["status"] = "missing_manifest_entry"
            details.append(detail)
            severity = "critical"
            continue

        if manifest_entry["kind"] == "file":
            secret_path = Path(manifest_entry["path"]).expanduser()
            detail["path"] = str(secret_path)
            if not secret_path.exists():
                detail["status"] = "missing_local_file"
                details.append(detail)
                severity = "critical"
                continue

        if days_remaining < 0:
            detail["status"] = "overdue"
            details.append(detail)
            severity = "critical"
        elif days_remaining <= secret["warning_window_days"]:
            detail["status"] = "warning_window"
            details.append(detail)
            if severity_rank[severity] < severity_rank["warning"]:
                severity = "warning"
        else:
            detail["status"] = "within_policy"
            details.append(detail)

    summary = "All tracked secrets are within their declared rotation period."
    if severity == "warning":
        summary = "One or more tracked secrets are inside their rotation warning window."
    elif severity == "critical":
        summary = "One or more tracked secrets are overdue, missing, or no longer match the local secret contract."

    return make_finding(
        check="check-secret-ages",
        severity=severity,
        summary=summary,
        details=details,
        run_id=run_id,
        outputs={"tracked_secret_count": len(catalog["secrets"])},
    )


def parse_not_after(payload: str) -> tuple[str | None, datetime | None]:
    subject = None
    expires = None
    for line in payload.splitlines():
        if line.startswith("subject="):
            subject = line.removeprefix("subject=").strip()
        if line.startswith("notAfter="):
            expires = datetime.strptime(line.removeprefix("notAfter=").strip(), "%b %d %H:%M:%S %Y %Z").replace(
                tzinfo=UTC
            )
    return subject, expires


def check_certificate_expiry(context: dict[str, Any], run_id: str) -> dict[str, Any]:
    del context
    severity_rank = {"ok": 0, "warning": 1, "critical": 2}
    severity = "ok"
    details: list[dict[str, Any]] = []
    for result in collect_certificate_results(now=utc_now()):
        detail = {
            "certificate_id": result["certificate_id"],
            "status": result["status"],
        }
        for field in ("subject", "issuer", "not_after", "days_remaining", "expected_issuer", "error"):
            if field in result:
                detail[field] = result[field]
        details.append(detail)
        if severity_rank[result["severity"]] > severity_rank[severity]:
            severity = result["severity"]

    summary = "All tracked certificates are within the configured renewal policy."
    if severity == "warning":
        summary = "One or more tracked certificates need renewal attention soon."
    elif severity == "critical":
        summary = "One or more tracked certificates are expired, near expiry, or could not be verified."
    return make_finding(
        check="check-certificate-expiry",
        severity=severity,
        summary=summary,
        details=details,
        run_id=run_id,
    )


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


def extract_backup_timestamp(volid: str) -> datetime | None:
    match = re.search(r"/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$", volid)
    if match is None:
        return None
    return parse_date(match.group(1))


def check_backup_recency(context: dict[str, Any], run_id: str) -> dict[str, Any]:
    result = execute_runner(
        context,
        "host_ssh",
        "proxmox_florin",
        "sudo pvesm list lv3-backup-pbs",
    )
    if result.returncode != 0:
        return make_finding(
            check="check-backup-recency",
            severity="critical",
            summary="Unable to read PBS backup content from the Proxmox host.",
            details=[
                {
                    "command": result.command,
                    "returncode": result.returncode,
                    "stdout": truncate(result.stdout),
                    "stderr": truncate(result.stderr),
                }
            ],
            run_id=run_id,
        )

    desired_vmids = [str(guest["vmid"]) for guest in context["host_vars"]["proxmox_guests"]]
    rows = parse_pvesm_rows(result.stdout)
    latest_by_vmid: dict[str, datetime] = {}
    for row in rows:
        ts = extract_backup_timestamp(row["volid"])
        if ts is None:
            continue
        current = latest_by_vmid.get(row["vmid"])
        if current is None or ts > current:
            latest_by_vmid[row["vmid"]] = ts

    now = utc_now()
    details: list[dict[str, Any]] = []
    severity = "ok"
    for vmid in desired_vmids:
        latest = latest_by_vmid.get(vmid)
        if latest is None:
            details.append({"vmid": vmid, "status": "missing_backup"})
            severity = "critical"
            continue
        age_hours = math.floor((now - latest).total_seconds() / 3600)
        entry = {
            "vmid": vmid,
            "latest_backup_at": isoformat(latest),
            "age_hours": age_hours,
        }
        if age_hours > 36:
            entry["status"] = "stale_backup"
            severity = "critical"
        else:
            entry["status"] = "ok"
        details.append(entry)

    summary = "All managed guests have PBS backups newer than 36 hours."
    if severity == "critical":
        summary = "One or more managed guests are missing PBS backups or only have stale recovery points."
    return make_finding(
        check="check-backup-recency",
        severity=severity,
        summary=summary,
        details=details,
        run_id=run_id,
    )


CHECK_HANDLERS = {
    "check-vm-state": check_vm_state,
    "check-service-health": check_service_health,
    "check-image-freshness": check_image_freshness,
    "check-secret-ages": check_secret_ages,
    "check-certificate-expiry": check_certificate_expiry,
    "check-backup-recency": check_backup_recency,
}


def build_daily_digest(findings: list[dict[str, Any]]) -> str:
    lines = [
        "# LV3 Platform Findings",
        "",
        f"Generated: {isoformat(utc_now())}",
        "",
    ]
    for finding in findings:
        lines.append(f"## {finding['check']} [{finding['severity']}]")
        lines.append(finding["summary"])
        lines.append("")
        for detail in finding["details"][:10]:
            lines.append(f"- {json.dumps(detail, sort_keys=True)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def publish_nats(context: dict[str, Any], subject: str, payload: dict[str, Any]) -> None:
    envelope = build_envelope(subject, payload, actor_id="agent/observation-loop", ts=payload.get("ts"))
    encoded = base64.b64encode(json.dumps(envelope, separators=(",", ":")).encode()).decode()
    remote_command = (
        "python3 - <<'PY'\n"
        "import base64, socket\n"
        f"subject = {subject!r}\n"
        f"payload = base64.b64decode({encoded!r})\n"
        "sock = socket.create_connection(('127.0.0.1', 4222), timeout=5)\n"
        "sock.sendall(b'CONNECT {\"verbose\":false}\\r\\n')\n"
        "sock.sendall(f'PUB {subject} {len(payload)}\\r\\n'.encode() + payload + b'\\r\\n')\n"
        "sock.close()\n"
        "PY"
    )
    result = execute_runner(context, "guest_jump", "docker-runtime-lv3", remote_command)
    if result.returncode != 0:
        raise RuntimeError(f"NATS publish failed for {subject}: {result.stderr or result.stdout}")


def post_json_webhook(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 300:
            raise RuntimeError(f"Webhook POST failed with HTTP {response.status}")


def maybe_read_secret_path(secret_manifest: dict[str, Any], secret_id: str) -> str | None:
    secret = secret_manifest["secrets"].get(secret_id)
    if secret is None or secret.get("kind") != "file":
        return None
    path = Path(secret["path"]).expanduser()
    if not path.exists():
        return None
    return path.read_text().strip()


def write_outputs(findings: list[dict[str, Any]], output_dir: Path, digest_path: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "findings.json", findings, indent=2, sort_keys=True)
    for finding in findings:
        write_json(output_dir / f"{finding['check']}.json", finding, indent=2, sort_keys=True)
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(build_daily_digest(findings))


def run_checks(args: argparse.Namespace) -> int:
    context = load_observation_context()
    run_id = str(uuid.uuid4())
    checks = args.checks or list(CHECK_HANDLERS)
    findings = [CHECK_HANDLERS[check](context, run_id) for check in checks]
    findings = suppress_findings_for_maintenance(findings, list_active_windows_best_effort(context))

    output_dir = Path(args.output_dir).expanduser()
    digest_path = Path(args.digest_path).expanduser()
    write_outputs(findings, output_dir, digest_path)

    if args.publish_nats:
        for finding in findings:
            publish_nats(context, "platform.findings.observation", finding)

    mattermost_url = args.mattermost_webhook_url or maybe_read_secret_path(
        context["secret_manifest"], "mattermost_platform_findings_webhook_url"
    )
    if mattermost_url:
        for finding in findings:
            if finding["severity"] in {"ok", "suppressed"}:
                continue
            post_json_webhook(
                mattermost_url,
                {
                    "text": f"[{finding['severity']}] {finding['check']}: {finding['summary']}",
                },
            )

    glitchtip_url = args.glitchtip_event_url or maybe_read_secret_path(
        context["secret_manifest"], "glitchtip_platform_findings_event_url"
    )
    if glitchtip_url:
        for finding in findings:
            if finding["severity"] in {"ok", "suppressed"}:
                continue
            post_json_webhook(
                glitchtip_url,
                {
                    "message": finding["summary"],
                    "level": "warning" if finding["severity"] == "warning" else "error",
                    "tags": {
                        "check": finding["check"],
                        "run_id": finding["run_id"],
                    },
                    "extra": {
                        "details": finding["details"],
                    },
                },
            )

    print(json.dumps(findings, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the platform observation loop checks.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where finding JSON artifacts should be written.",
    )
    parser.add_argument(
        "--digest-path",
        default=str(DEFAULT_DIGEST_PATH),
        help="Markdown digest path written for Open WebUI operator review.",
    )
    parser.add_argument(
        "--publish-nats",
        action="store_true",
        help="Publish each finding to NATS via docker-runtime-lv3.",
    )
    parser.add_argument(
        "--mattermost-webhook-url",
        help="Optional Mattermost incoming webhook URL for non-ok findings.",
    )
    parser.add_argument(
        "--glitchtip-event-url",
        help="Optional GlitchTip-compatible ingestion URL for non-ok findings.",
    )
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=sorted(CHECK_HANDLERS),
        help="Run only a subset of the defined checks.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run_checks(args)
    except (OSError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Platform observation", exc)


if __name__ == "__main__":
    sys.exit(main())
