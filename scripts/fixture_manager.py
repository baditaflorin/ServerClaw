#!/usr/bin/env python3
"""Provision and manage ephemeral Proxmox VM fixtures."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import vmid_allocator


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DEFINITIONS_DIR = REPO_ROOT / "tests" / "fixtures"
FIXTURE_RECEIPTS_DIR = REPO_ROOT / "receipts" / "fixtures"
FIXTURE_LOCAL_ROOT = REPO_ROOT / ".local" / "fixtures"
FIXTURE_RUNTIME_DIR = FIXTURE_LOCAL_ROOT / "runtime"
FIXTURE_ARCHIVE_DIR = FIXTURE_LOCAL_ROOT / "archive"
FIXTURE_LOCKS_DIR = FIXTURE_LOCAL_ROOT / "locks"
CONTROLLER_SECRETS_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
TEMPLATE_MANIFEST_PATH = REPO_ROOT / "config" / "vm-template-manifest.json"
GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "all.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
TOFU_IMAGE = os.environ.get("TOFU_IMAGE", "registry.lv3.org/check-runner/infra:2026.03.23")
TOFU_PLATFORM = os.environ.get("TOFU_PLATFORM", "linux/amd64")
TOFU_DOCKER_NETWORK = os.environ.get("TOFU_DOCKER_NETWORK", "host")


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def compact_timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_fixture_definition(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
            raise RuntimeError("PyYAML is required for non-JSON fixture definitions.") from exc
        payload = yaml.safe_load(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Fixture definition must be a mapping: {path}")
    return payload


def resolve_fixture_path(fixture_name: str) -> Path:
    candidates = [
        FIXTURE_DEFINITIONS_DIR / f"{fixture_name}.yml",
        FIXTURE_DEFINITIONS_DIR / f"{fixture_name}-fixture.yml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Unknown fixture '{fixture_name}'")


def yaml_scalar(path: Path, key: str, default: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+?)\s*$", flags=re.MULTILINE)
    match = pattern.search(path.read_text(encoding="utf-8"))
    if not match:
        return default
    return match.group(1).strip().strip("\"'")


def controller_secret_path(secret_id: str) -> Path:
    payload = load_json(CONTROLLER_SECRETS_PATH)
    return Path(payload["secrets"][secret_id]["path"])


def default_fixture_context() -> dict[str, str]:
    return {
        "node_name": "proxmox_florin",
        "template_node_name": "proxmox_florin",
        "datastore_id": yaml_scalar(GROUP_VARS_PATH, "proxmox_storage_id", "local"),
        "cloud_init_datastore_id": yaml_scalar(GROUP_VARS_PATH, "proxmox_snippets_storage_id", "local"),
        "ci_user": yaml_scalar(GROUP_VARS_PATH, "proxmox_guest_ci_user", "ops"),
        "nameserver": yaml_scalar(GROUP_VARS_PATH, "proxmox_guest_nameserver", "1.1.1.1"),
        "search_domain": yaml_scalar(GROUP_VARS_PATH, "proxmox_guest_searchdomain", "lv3.org"),
        "jump_user": yaml_scalar(GROUP_VARS_PATH, "proxmox_host_admin_user", "ops"),
        "jump_host": yaml_scalar(HOST_VARS_PATH, "management_ipv4", "65.108.75.123"),
    }


def bootstrap_private_key() -> Path:
    return controller_secret_path("bootstrap_ssh_private_key")


def bootstrap_public_key() -> str:
    private_key = bootstrap_private_key()
    public_key = Path(f"{private_key}.pub")
    if public_key.exists():
        return public_key.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Missing public bootstrap key: {public_key}")


def proxmox_api_credentials() -> tuple[str, str]:
    return vmid_allocator.read_api_credentials()


def template_vmid(template_name: str) -> int:
    manifest = load_json(TEMPLATE_MANIFEST_PATH)
    templates = manifest.get("templates", {})
    template = templates.get(template_name)
    if not isinstance(template, dict):
        raise KeyError(f"Unknown template '{template_name}' in {TEMPLATE_MANIFEST_PATH}")
    return int(template["vmid"])


def parse_ip_cidr(value: str) -> tuple[str, int]:
    ip_text, separator, cidr_text = value.partition("/")
    if separator != "/" or not cidr_text.isdigit():
        raise ValueError(f"Expected ip/cidr, got '{value}'")
    return ip_text, int(cidr_text)


def mac_from_vmid(vmid: int) -> str:
    octets = [0xBC, 0x24, 0x11, (vmid >> 16) & 0xFF, (vmid >> 8) & 0xFF, vmid & 0xFF]
    return ":".join(f"{octet:02X}" for octet in octets)


def receipt_path(receipt_id: str) -> Path:
    return FIXTURE_RECEIPTS_DIR / f"{receipt_id}.json"


def list_receipt_paths() -> list[Path]:
    if not FIXTURE_RECEIPTS_DIR.exists():
        return []
    return sorted(
        path
        for path in FIXTURE_RECEIPTS_DIR.glob("*.json")
        if not path.name.startswith("reaper-run-")
    )


def load_receipt(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid receipt payload: {path}")
    payload.setdefault("receipt_path", str(path))
    return payload


def active_receipts(fixture_name: str | None = None) -> list[dict[str, Any]]:
    receipts = []
    for path in list_receipt_paths():
        payload = load_receipt(path)
        if payload.get("status") not in {"provisioning", "active"}:
            continue
        if fixture_name and payload.get("fixture_id") != fixture_name:
            continue
        receipts.append(payload)
    return sorted(receipts, key=lambda item: item["created_at"])


def format_duration(delta: dt.timedelta) -> str:
    seconds = int(delta.total_seconds())
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{sign}{hours}h{minutes:02d}m"
    return f"{sign}{minutes}m"


def expiry_for_receipt(receipt: dict[str, Any]) -> dt.datetime:
    created_at = parse_timestamp(receipt["created_at"])
    minutes = int(receipt.get("lifetime_minutes", 0)) + int(receipt.get("extend_minutes", 0))
    return created_at + dt.timedelta(minutes=minutes)


def build_runtime_main(receipt: dict[str, Any]) -> str:
    definition = receipt["definition"]
    fixture_context = receipt["context"]
    network_ip, network_cidr = parse_ip_cidr(definition["network"]["ip_cidr"])
    tags = list(dict.fromkeys([*definition.get("tags", []), receipt["receipt_id"]]))
    module_path = REPO_ROOT / "tofu" / "modules" / "proxmox-fixture"
    assignments = {
        "fixture_id": definition["fixture_id"],
        "name": f"{definition['fixture_id']}-{receipt['vm_id']}",
        "description": f"ephemeral fixture {definition['fixture_id']}",
        "node_name": fixture_context["node_name"],
        "vm_id": receipt["vm_id"],
        "vmid_range": definition["vmid_range"],
        "lifetime_minutes": definition["lifetime_minutes"],
        "template_node_name": fixture_context["template_node_name"],
        "template_vmid": template_vmid(definition["template"]),
        "datastore_id": fixture_context["datastore_id"],
        "cloud_init_datastore_id": fixture_context["cloud_init_datastore_id"],
        "cores": definition["resources"]["cores"],
        "memory_mb": definition["resources"]["memory_mb"],
        "disk_gb": definition["resources"]["disk_gb"],
        "bridge": definition["network"]["bridge"],
        "mac_address": receipt["mac_address"],
        "ip_address": network_ip,
        "ip_cidr": network_cidr,
        "gateway": definition["network"]["gateway"],
        "nameserver": definition.get("nameserver", fixture_context["nameserver"]),
        "search_domain": definition.get("search_domain", fixture_context["search_domain"]),
        "tags": tags,
        "ci_user": definition.get("ssh_user", fixture_context["ci_user"]),
        "ssh_authorized_keys": [bootstrap_public_key()],
    }
    lines = [
        'terraform {',
        '  required_version = ">= 1.10.0"',
        '  required_providers {',
        '    proxmox = {',
        '      source  = "bpg/proxmox"',
        '      version = "= 0.99.0"',
        '    }',
        '  }',
        '}',
        "",
        'variable "proxmox_endpoint" {',
        "  type      = string",
        "  sensitive = true",
        "}",
        "",
        'variable "proxmox_api_token" {',
        "  type      = string",
        "  sensitive = true",
        "}",
        "",
        'provider "proxmox" {',
        "  endpoint  = var.proxmox_endpoint",
        "  api_token = var.proxmox_api_token",
        "  insecure  = true",
        "}",
        "",
        'module "fixture" {',
        f"  source = {json.dumps(str(module_path))}",
    ]
    for key, value in assignments.items():
        lines.append(f"  {key} = {json.dumps(value)}")
    lines.extend(
        [
            "}",
            "",
            'output "vm_id" {',
            "  value = module.fixture.vm_id",
            "}",
            "",
            'output "ip_address" {',
            "  value = module.fixture.ip_address",
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


def ensure_runtime_files(receipt: dict[str, Any]) -> Path:
    runtime_dir = REPO_ROOT / receipt["runtime_dir"]
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "main.tf").write_text(build_runtime_main(receipt), encoding="utf-8")
    return runtime_dir


def run_command(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult:
    completed = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandResult(
        argv=argv,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def ensure_command(result: CommandResult, action: str) -> None:
    if result.returncode == 0:
        return
    message = result.stderr or result.stdout or f"{action} failed"
    raise RuntimeError(f"{action}: {message}")


def tofu_command(runtime_dir: Path, *args: str) -> list[str]:
    if shutil.which("tofu"):
        return ["tofu", *args]
    if not shutil.which("docker"):
        raise RuntimeError("Missing both 'tofu' and 'docker' required for fixture provisioning")
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        TOFU_PLATFORM,
        "-v",
        f"{REPO_ROOT}:/workspace",
        "-v",
        f"{runtime_dir}:/runtime",
        "-w",
        "/runtime",
    ]
    if TOFU_DOCKER_NETWORK:
        command.extend(["--network", TOFU_DOCKER_NETWORK])
    command.extend([TOFU_IMAGE, "tofu", *args])
    return command


def apply_fixture(runtime_dir: Path, endpoint: str, api_token: str) -> None:
    env = os.environ.copy()
    env["TF_VAR_proxmox_endpoint"] = endpoint
    env["TF_VAR_proxmox_api_token"] = api_token
    ensure_command(run_command(tofu_command(runtime_dir, "init", "-backend=false", "-input=false"), cwd=runtime_dir, env=env), "tofu init")
    ensure_command(
        run_command(
            tofu_command(runtime_dir, "apply", "-auto-approve", "-input=false", "-lock-timeout=60s"),
            cwd=runtime_dir,
            env=env,
        ),
        "tofu apply",
    )


def destroy_fixture(runtime_dir: Path, endpoint: str, api_token: str) -> None:
    if not runtime_dir.exists():
        return
    env = os.environ.copy()
    env["TF_VAR_proxmox_endpoint"] = endpoint
    env["TF_VAR_proxmox_api_token"] = api_token
    ensure_command(run_command(tofu_command(runtime_dir, "init", "-backend=false", "-input=false"), cwd=runtime_dir, env=env), "tofu init")
    ensure_command(
        run_command(
            tofu_command(runtime_dir, "destroy", "-auto-approve", "-input=false", "-lock-timeout=60s"),
            cwd=runtime_dir,
            env=env,
        ),
        "tofu destroy",
    )


def ssh_argv(receipt: dict[str, Any], remote_command: str, *, timeout_seconds: int = 5) -> list[str]:
    key_path = bootstrap_private_key()
    jump_user = receipt["context"]["jump_user"]
    jump_host = receipt["context"]["jump_host"]
    ssh_user = receipt["definition"].get("ssh_user", receipt["context"]["ci_user"])
    proxy = f'ssh -i {key_path} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 {jump_user}@{jump_host} -W %h:%p'
    return [
        "ssh",
        "-i",
        str(key_path),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout_seconds}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        f"ProxyCommand={proxy}",
        f"{ssh_user}@{receipt['ip_address']}",
        remote_command,
    ]


def wait_for_ssh(receipt: dict[str, Any], timeout_seconds: int = 300) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = run_command(ssh_argv(receipt, "true"))
        if result.returncode == 0:
            return
        time.sleep(5)
    raise RuntimeError(f"SSH did not become ready for fixture {receipt['receipt_id']}")


def ansible_inventory(receipt: dict[str, Any]) -> dict[str, Any]:
    key_path = bootstrap_private_key()
    jump_user = receipt["context"]["jump_user"]
    jump_host = receipt["context"]["jump_host"]
    proxy = f'-o IdentitiesOnly=yes -o ProxyCommand="ssh -i {key_path} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 {jump_user}@{jump_host} -W %h:%p"'
    ssh_user = receipt["definition"].get("ssh_user", receipt["context"]["ci_user"])
    return {
        "all": {
            "hosts": {
                "fixture": {
                    "ansible_host": receipt["ip_address"],
                    "ansible_user": ssh_user,
                    "ansible_become": True,
                    "ansible_python_interpreter": "/usr/bin/python3",
                    "ansible_ssh_private_key_file": str(key_path),
                    "ansible_ssh_common_args": proxy,
                }
            }
        }
    }


def converge_roles(receipt: dict[str, Any], *, skip_roles: bool = False) -> None:
    roles = receipt["definition"].get("roles_under_test", [])
    if skip_roles or not roles:
        return
    runtime_dir = REPO_ROOT / receipt["runtime_dir"]
    inventory_path = runtime_dir / "inventory.json"
    playbook_path = runtime_dir / "converge.json"
    write_json(inventory_path, ansible_inventory(receipt))
    playbook = [
        {
            "name": "Converge ephemeral fixture roles",
            "hosts": "fixture",
            "gather_facts": True,
            "become": True,
            "vars_files": [str(GROUP_VARS_PATH), str(HOST_VARS_PATH)],
            "roles": roles,
        }
    ]
    write_json(playbook_path, playbook)
    ensure_command(
        run_command(["ansible-playbook", "-i", str(inventory_path), str(playbook_path)], cwd=REPO_ROOT),
        "ansible-playbook converge",
    )


def verify_http(url: str, expected_status: int, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "fixture-manager/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            observed = response.status
    except urllib.error.URLError as exc:
        return {"ok": False, "kind": "http", "target": url, "error": str(exc)}
    return {"ok": observed == expected_status, "kind": "http", "target": url, "status": observed, "expected_status": expected_status}


def verify_tcp(host: str, port: int, timeout_seconds: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {"ok": True, "kind": "tcp", "target": f"{host}:{port}"}
    except OSError as exc:
        return {"ok": False, "kind": "tcp", "target": f"{host}:{port}", "error": str(exc)}


def verify_command(receipt: dict[str, Any], command: str, timeout_seconds: int) -> dict[str, Any]:
    result = run_command(ssh_argv(receipt, command, timeout_seconds=timeout_seconds))
    return {
        "ok": result.returncode == 0,
        "kind": "command",
        "target": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def verify_fixture(receipt: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for item in definition.get("verify", []):
        timeout_seconds = int(item.get("timeout_seconds", 30))
        if "url" in item:
            checks.append(verify_http(item["url"], int(item.get("expected_status", 200)), timeout_seconds))
            continue
        if "port" in item:
            checks.append(verify_tcp(receipt["ip_address"], int(item["port"]), timeout_seconds))
            continue
        if "command" in item:
            checks.append(verify_command(receipt, item["command"], timeout_seconds))
            continue
        checks.append({"ok": False, "kind": "unknown", "target": json.dumps(item, sort_keys=True), "error": "Unsupported verify block"})
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def capture_ssh_fingerprint(receipt: dict[str, Any]) -> str:
    if not shutil.which("ssh-keyscan") or not shutil.which("ssh-keygen"):
        return ""
    keyscan = run_command(["ssh-keyscan", "-T", "5", receipt["ip_address"]])
    if keyscan.returncode != 0 or not keyscan.stdout:
        return ""
    keygen = subprocess.run(
        ["ssh-keygen", "-lf", "-"],
        input=keyscan.stdout,
        text=True,
        capture_output=True,
        check=False,
    )
    if keygen.returncode != 0:
        return ""
    return keygen.stdout.strip()


def allocator_lock() -> Any:
    FIXTURE_LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    handle = (FIXTURE_LOCKS_DIR / "vmid.lock").open("w", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def reserved_vmids() -> set[int]:
    return {int(receipt["vm_id"]) for receipt in active_receipts()}


def build_receipt(definition: dict[str, Any], fixture_path: Path, vm_id: int, now: dt.datetime) -> dict[str, Any]:
    network_ip, _network_cidr = parse_ip_cidr(definition["network"]["ip_cidr"])
    receipt_id = f"{definition['fixture_id']}-{compact_timestamp(now)}"
    context = default_fixture_context()
    runtime_dir = FIXTURE_RUNTIME_DIR / receipt_id
    return {
        "receipt_id": receipt_id,
        "fixture_id": definition["fixture_id"],
        "status": "provisioning",
        "created_at": isoformat(now),
        "updated_at": isoformat(now),
        "lifetime_minutes": int(definition["lifetime_minutes"]),
        "extend_minutes": int(definition.get("extend_minutes", 0)),
        "definition_path": str(fixture_path.relative_to(REPO_ROOT)),
        "runtime_dir": str(runtime_dir.relative_to(REPO_ROOT)),
        "vm_id": vm_id,
        "ip_address": network_ip,
        "mac_address": definition.get("mac_address", mac_from_vmid(vm_id)),
        "definition": definition,
        "context": context,
    }


def save_receipt(receipt: dict[str, Any]) -> Path:
    receipt["updated_at"] = isoformat(utc_now())
    path = receipt_path(receipt["receipt_id"])
    write_json(path, receipt)
    return path


def archive_receipt(receipt: dict[str, Any]) -> None:
    archive_path = FIXTURE_ARCHIVE_DIR / f"{receipt['receipt_id']}.json"
    write_json(archive_path, receipt)


def release_receipt(receipt: dict[str, Any]) -> None:
    path = receipt_path(receipt["receipt_id"])
    if path.exists():
        path.unlink()


def fixture_up(fixture_name: str, *, skip_roles: bool = False, skip_verify: bool = False) -> dict[str, Any]:
    fixture_path = resolve_fixture_path(fixture_name)
    definition = load_fixture_definition(fixture_path)
    start, end = tuple(int(value) for value in definition["vmid_range"])
    lock_handle = allocator_lock()
    try:
        endpoint, api_token = proxmox_api_credentials()
        used_vmids = vmid_allocator.fetch_cluster_vmids(endpoint, api_token) | reserved_vmids()
        vm_id = vmid_allocator.allocate_free_vmid(used_vmids, start, end)
        receipt = build_receipt(definition, fixture_path, vm_id, utc_now())
        save_receipt(receipt)
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()

    runtime_dir = ensure_runtime_files(receipt)
    try:
        apply_fixture(runtime_dir, endpoint, api_token)
        wait_for_ssh(receipt)
        converge_roles(receipt, skip_roles=skip_roles)
        verification = {"ok": True, "checks": []} if skip_verify else verify_fixture(receipt, definition)
        if not verification["ok"]:
            raise RuntimeError(f"Fixture verification failed for {receipt['receipt_id']}")
        receipt["status"] = "active"
        receipt["ssh_fingerprint"] = capture_ssh_fingerprint(receipt)
        receipt["verification"] = verification
        receipt["expires_at"] = isoformat(expiry_for_receipt(receipt))
        save_receipt(receipt)
    except Exception:
        try:
            destroy_fixture(runtime_dir, endpoint, api_token)
        except Exception:
            pass
        receipt["status"] = "failed"
        archive_receipt(receipt)
        release_receipt(receipt)
        raise
    return receipt


def fixture_down(fixture_name: str | None = None, *, receipt_id: str | None = None) -> dict[str, Any]:
    if not fixture_name and not receipt_id:
        raise ValueError("fixture_down requires a fixture name or receipt_id")
    receipts = active_receipts(fixture_name) if fixture_name else active_receipts()
    if receipt_id:
        receipts = [receipt for receipt in receipts if receipt["receipt_id"] == receipt_id]
    endpoint, api_token = proxmox_api_credentials()
    destroyed = []
    for receipt in receipts:
        runtime_dir = REPO_ROOT / receipt["runtime_dir"]
        destroy_fixture(runtime_dir, endpoint, api_token)
        receipt["status"] = "destroyed"
        receipt["destroyed_at"] = isoformat(utc_now())
        archive_receipt(receipt)
        release_receipt(receipt)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
        destroyed.append({"receipt_id": receipt["receipt_id"], "vm_id": receipt["vm_id"]})
    return {"fixture_id": fixture_name, "destroyed": destroyed}


def fixture_list(*, refresh_health: bool = True) -> list[dict[str, Any]]:
    rows = []
    for receipt in active_receipts():
        remaining = expiry_for_receipt(receipt) - utc_now()
        health = receipt.get("verification", {"ok": False})
        if refresh_health:
            health = verify_fixture(receipt, receipt["definition"])
        rows.append(
            {
                "fixture_id": receipt["fixture_id"],
                "receipt_id": receipt["receipt_id"],
                "vm_id": receipt["vm_id"],
                "ip_address": receipt["ip_address"],
                "age": format_duration(utc_now() - parse_timestamp(receipt["created_at"])),
                "remaining": format_duration(remaining),
                "health": "ok" if health.get("ok") else "failed",
                "status": receipt["status"],
            }
        )
    return rows


def reap_expired() -> dict[str, Any]:
    expired: list[str] = []
    skipped: list[str] = []
    for receipt in active_receipts():
        if expiry_for_receipt(receipt) > utc_now():
            skipped.append(receipt["receipt_id"])
            continue
        expired.append(receipt["receipt_id"])
        fixture_down(receipt_id=receipt["receipt_id"])
    summary = {
        "run_at": isoformat(utc_now()),
        "expired_receipts": expired,
        "skipped_receipts": skipped,
    }
    write_json(FIXTURE_RECEIPTS_DIR / f"reaper-run-{compact_timestamp(utc_now())}.json", summary)
    return summary


def render_fixture_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No active fixtures"
    headers = ("FIXTURE", "VMID", "IP", "AGE", "REMAINING", "HEALTH")
    widths = {
        "FIXTURE": max(len("FIXTURE"), *(len(row["fixture_id"]) for row in rows)),
        "VMID": max(len("VMID"), *(len(str(row["vm_id"])) for row in rows)),
        "IP": max(len("IP"), *(len(row["ip_address"]) for row in rows)),
        "AGE": max(len("AGE"), *(len(row["age"]) for row in rows)),
        "REMAINING": max(len("REMAINING"), *(len(row["remaining"]) for row in rows)),
        "HEALTH": max(len("HEALTH"), *(len(row["health"]) for row in rows)),
    }
    lines = [
        " ".join(
            [
                headers[0].ljust(widths["FIXTURE"]),
                headers[1].ljust(widths["VMID"]),
                headers[2].ljust(widths["IP"]),
                headers[3].ljust(widths["AGE"]),
                headers[4].ljust(widths["REMAINING"]),
                headers[5].ljust(widths["HEALTH"]),
            ]
        )
    ]
    for row in rows:
        lines.append(
            " ".join(
                [
                    row["fixture_id"].ljust(widths["FIXTURE"]),
                    str(row["vm_id"]).ljust(widths["VMID"]),
                    row["ip_address"].ljust(widths["IP"]),
                    row["age"].ljust(widths["AGE"]),
                    row["remaining"].ljust(widths["REMAINING"]),
                    row["health"].ljust(widths["HEALTH"]),
                ]
            )
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    up = subparsers.add_parser("up")
    up.add_argument("fixture_name")
    up.add_argument("--json", action="store_true")
    up.add_argument("--skip-role-converge", action="store_true")
    up.add_argument("--skip-verify", action="store_true")

    down = subparsers.add_parser("down")
    down.add_argument("fixture_name", nargs="?")
    down.add_argument("--receipt-id")
    down.add_argument("--json", action="store_true")

    fixture_list_parser = subparsers.add_parser("list")
    fixture_list_parser.add_argument("--json", action="store_true")
    fixture_list_parser.add_argument("--no-refresh-health", action="store_true")

    reap = subparsers.add_parser("reap-expired")
    reap.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    FIXTURE_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        if args.action == "up":
            payload = fixture_up(
                args.fixture_name,
                skip_roles=args.skip_role_converge,
                skip_verify=args.skip_verify,
            )
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(f"Fixture {payload['fixture_id']} ready: vmid={payload['vm_id']} ip={payload['ip_address']}")
            return 0
        if args.action == "down":
            payload = fixture_down(args.fixture_name, receipt_id=args.receipt_id)
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(f"Destroyed {len(payload['destroyed'])} fixture(s)")
            return 0
        if args.action == "list":
            rows = fixture_list(refresh_health=not args.no_refresh_health)
            if args.json:
                print(json.dumps(rows, indent=2, sort_keys=True))
            else:
                print(render_fixture_table(rows))
            return 0
        if args.action == "reap-expired":
            payload = reap_expired()
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(f"Expired fixtures destroyed: {len(payload['expired_receipts'])}")
            return 0
    except Exception as exc:
        print(f"fixture-manager error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
