#!/usr/bin/env python3

import argparse
import asyncio
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path, write_json
from mutation_audit import build_event, emit_event_best_effort


HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
GROUP_VARS_PATH = repo_path("inventory", "group_vars", "all.yml")
SECRET_MANIFEST_PATH = repo_path("config", "controller-local-secrets.json")
SCHEMA_PATH = repo_path("docs", "schema", "maintenance-window.json")

MAINTENANCE_BUCKET = "maintenance-windows"
MAINTENANCE_BUCKET_MAX_AGE_SECONDS = 2 * 60 * 60
MAINTENANCE_KEY_PREFIX = "maintenance/"
MAINTENANCE_STATE_FILE_ENV = "LV3_MAINTENANCE_WINDOWS_FILE"

DEFAULT_OPENED_BY_CLASS = "operator"
DEFAULT_OPENED_BY_ID = "ops-linux"
DEFAULT_CLOSED_BY_CLASS = "operator"
DEFAULT_CLOSED_BY_ID = "ops-linux"

SERVICE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
ALLOWED_OPENED_BY_CLASSES = {"operator", "agent"}
ALLOWED_FINDING_SEVERITIES = {"ok", "warning", "critical", "suppressed"}
UNSUPPRESSIBLE_FINDING_CHECKS = {"check-certificate-expiry", "check-secret-ages"}
NON_PROBLEM_DETAIL_STATUSES = {"ok", "local_build_ok", "pinned_ok", "within_policy"}


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def require_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_int(value: object, path: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def require_mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def state_file_path() -> Path | None:
    candidate = os.environ.get(MAINTENANCE_STATE_FILE_ENV, "").strip()
    if not candidate:
        return None
    return Path(candidate).expanduser()


def load_controller_context() -> dict[str, Any]:
    host_vars = load_yaml(HOST_VARS_PATH)
    group_vars = load_yaml(GROUP_VARS_PATH)
    secret_manifest = load_json(SECRET_MANIFEST_PATH)
    bootstrap_key = Path(secret_manifest["secrets"]["bootstrap_ssh_private_key"]["path"]).expanduser()
    guests = {guest["name"]: guest["ipv4"] for guest in host_vars["proxmox_guests"]}
    return {
        "host_vars": host_vars,
        "group_vars": group_vars,
        "secret_manifest": secret_manifest,
        "bootstrap_key": bootstrap_key,
        "host_user": group_vars["proxmox_host_admin_user"],
        "host_addr": host_vars["management_tailscale_ipv4"],
        "guests": guests,
    }


def resolve_nats_credentials(context: dict[str, Any]) -> dict[str, str]:
    env_user = os.environ.get("LV3_NATS_USERNAME", "").strip()
    env_password = os.environ.get("LV3_NATS_PASSWORD", "").strip()
    env_password_file = os.environ.get("LV3_NATS_PASSWORD_FILE", "").strip()
    if env_password_file and not env_password:
        env_password = Path(env_password_file).expanduser().read_text().strip()
    if env_user and env_password:
        return {"user": env_user, "password": env_password}

    secret_entry = context["secret_manifest"]["secrets"].get("nats_jetstream_admin_password")
    if isinstance(secret_entry, dict) and secret_entry.get("kind") == "file":
        password_path = Path(secret_entry["path"]).expanduser()
        if password_path.exists():
            return {
                "user": "jetstream-admin",
                "password": password_path.read_text().strip(),
            }
    return {}


def build_guest_ssh_command(context: dict[str, Any], target: str, *extra_args: str) -> list[str]:
    key_path = str(context["bootstrap_key"])
    guest_ip = context["guests"][target]
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
        f"{context['host_user']}@{guest_ip}",
        *extra_args,
    ]


def reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def wait_for_tunnel(process: subprocess.Popen[str], port: int) -> None:
    deadline = time.time() + 10
    last_error: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise RuntimeError(f"SSH tunnel failed: {(stderr or stdout).strip()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for SSH tunnel on localhost:{port}: {last_error}")


@contextmanager
def nats_tunnel(context: dict[str, Any]) -> int:
    local_port = reserve_local_port()
    command = build_guest_ssh_command(
        context,
        "docker-runtime-lv3",
        "-N",
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:4222",
        "-o",
        "ExitOnForwardFailure=yes",
    )
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for_tunnel(process, local_port)
        yield local_port
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def maintenance_key(service_id: str) -> str:
    return f"{MAINTENANCE_KEY_PREFIX}{service_id}"


def strip_maintenance_prefix(key: str) -> str:
    if key.startswith(MAINTENANCE_KEY_PREFIX):
        return key.removeprefix(MAINTENANCE_KEY_PREFIX)
    return key


def validate_opened_by_class(value: str, path: str) -> str:
    value = require_string(value, path)
    if value not in ALLOWED_OPENED_BY_CLASSES:
        raise ValueError(f"{path} must be one of {sorted(ALLOWED_OPENED_BY_CLASSES)}")
    return value


def validate_service_id(service_id: str, path: str = "service_id") -> str:
    service_id = require_string(service_id, path)
    if service_id == "all":
        return service_id
    import re

    if not re.match(SERVICE_ID_PATTERN, service_id):
        raise ValueError(f"{path} must be 'all' or a lowercase service identifier")
    return service_id


def validate_maintenance_window(window: dict[str, Any], path: str = "maintenance window") -> dict[str, Any]:
    window = require_mapping(window, path)
    require_string(window.get("window_id"), f"{path}.window_id")
    validate_service_id(window.get("service_id"), f"{path}.service_id")
    require_string(window.get("reason"), f"{path}.reason")
    opened_by = require_mapping(window.get("opened_by"), f"{path}.opened_by")
    validate_opened_by_class(opened_by.get("class"), f"{path}.opened_by.class")
    require_string(opened_by.get("id"), f"{path}.opened_by.id")
    parse_datetime(require_string(window.get("opened_at"), f"{path}.opened_at"))
    require_int(window.get("expected_duration_minutes"), f"{path}.expected_duration_minutes", 1)
    parse_datetime(require_string(window.get("auto_close_at"), f"{path}.auto_close_at"))
    correlation_id = window.get("correlation_id")
    if correlation_id is not None:
        require_string(correlation_id, f"{path}.correlation_id")
    return window


def build_maintenance_window(
    *,
    service_id: str,
    reason: str,
    duration_minutes: int,
    opened_by_class: str,
    opened_by_id: str,
    correlation_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    service_id = validate_service_id(service_id)
    reason = require_string(reason, "reason")
    duration_minutes = require_int(duration_minutes, "duration_minutes", 1)
    opened_by_class = validate_opened_by_class(opened_by_class, "opened_by_class")
    opened_by_id = require_string(opened_by_id, "opened_by_id")
    now = now or utc_now()
    auto_close_at = now + timedelta(minutes=duration_minutes)
    return validate_maintenance_window(
        {
            "window_id": str(uuid.uuid4()),
            "service_id": service_id,
            "reason": reason,
            "opened_by": {
                "class": opened_by_class,
                "id": opened_by_id,
            },
            "opened_at": isoformat(now),
            "expected_duration_minutes": duration_minutes,
            "auto_close_at": isoformat(auto_close_at),
            "correlation_id": correlation_id or f"maintenance:{service_id}:{now.strftime('%Y%m%dT%H%M%SZ')}",
        }
    )


def load_local_state() -> dict[str, dict[str, Any]]:
    path = state_file_path()
    if path is None:
        raise RuntimeError(f"{MAINTENANCE_STATE_FILE_ENV} is not set")
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    raw = require_mapping(raw, str(path))
    active: dict[str, dict[str, Any]] = {}
    now = utc_now()
    for key, window in raw.items():
        key = require_string(key, f"{path} key '{key}'")
        validated = validate_maintenance_window(window, f"{path}.{key}")
        if parse_datetime(validated["auto_close_at"]) <= now:
            continue
        active[key] = validated
    if active != raw:
        write_json(path, active, indent=2, sort_keys=True)
    return active


def save_local_state(state: dict[str, dict[str, Any]]) -> None:
    path = state_file_path()
    if path is None:
        raise RuntimeError(f"{MAINTENANCE_STATE_FILE_ENV} is not set")
    write_json(path, state, indent=2, sort_keys=True)


async def connect_jetstream(nats_url: str, credentials: dict[str, str] | None = None):
    from nats.aio.client import Client as NATS

    async def error_cb(error: Exception) -> None:
        recorded_errors.append(error)

    nc = NATS()
    recorded_errors: list[Exception] = []
    setattr(nc, "_lv3_recorded_errors", recorded_errors)
    connect_kwargs: dict[str, Any] = {
        "servers": [nats_url],
        "error_cb": error_cb,
        "connect_timeout": 5,
        "allow_reconnect": False,
        "max_reconnect_attempts": 0,
        "reconnect_time_wait": 0,
    }
    if credentials:
        connect_kwargs.update(credentials)
    await nc.connect(**connect_kwargs)
    return nc, nc.jetstream()


def raise_recorded_nats_error(nc: Any, fallback: Exception) -> None:
    recorded_errors = getattr(nc, "_lv3_recorded_errors", [])
    if recorded_errors:
        raise RuntimeError(str(recorded_errors[-1])) from fallback
    raise fallback


async def get_bucket(js: Any, *, create: bool) -> Any | None:
    import nats.js.errors

    try:
        return await js.key_value(MAINTENANCE_BUCKET)
    except nats.js.errors.BucketNotFoundError:
        if not create:
            return None
    return await js.create_key_value(
        bucket=MAINTENANCE_BUCKET,
        description="Planned maintenance windows for suppressing expected alert noise.",
        history=1,
        ttl=MAINTENANCE_BUCKET_MAX_AGE_SECONDS,
        direct=True,
    )


async def publish_event(nc: Any, subject: str, payload: dict[str, Any]) -> None:
    await nc.publish(subject, json.dumps(payload, separators=(",", ":")).encode())
    await nc.flush(timeout=5)


async def ensure_bucket_async(nats_url: str, credentials: dict[str, str] | None = None) -> dict[str, Any]:
    nc, js = await connect_jetstream(nats_url, credentials)
    try:
        await get_bucket(js, create=True)
        return {"status": "ready", "bucket": MAINTENANCE_BUCKET}
    finally:
        await nc.drain()


async def list_windows_async(
    nats_url: str,
    credentials: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    import nats.js.errors

    nc, js = await connect_jetstream(nats_url, credentials)
    try:
        kv = await get_bucket(js, create=False)
        if kv is None:
            return {}
        try:
            keys = await kv.keys()
        except nats.js.errors.NoKeysError:
            return {}

        active: dict[str, dict[str, Any]] = {}
        for key in sorted(keys):
            if not key.startswith(MAINTENANCE_KEY_PREFIX):
                continue
            try:
                entry = await kv.get(key)
            except (nats.js.errors.KeyNotFoundError, nats.js.errors.KeyDeletedError):
                continue
            window = validate_maintenance_window(json.loads(entry.value.decode()), key)
            if parse_datetime(window["auto_close_at"]) <= utc_now():
                continue
            active[key] = window
        return active
    finally:
        await nc.drain()


async def open_window_async(
    nats_url: str,
    window: dict[str, Any],
    credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    import nats.js.errors

    nc, js = await connect_jetstream(nats_url, credentials)
    try:
        kv = await get_bucket(js, create=True)
        key = maintenance_key(window["service_id"])
        payload = json.dumps(window, separators=(",", ":")).encode()
        ttl_seconds = max(1, int((parse_datetime(window["auto_close_at"]) - utc_now()).total_seconds()))

        try:
            current = await kv.get(key)
            revision = current.revision
            await kv.update(key, payload, last=revision, msg_ttl=ttl_seconds)
            action = "updated"
        except (nats.js.errors.KeyNotFoundError, nats.js.errors.KeyDeletedError):
            await kv.create(key, payload, msg_ttl=ttl_seconds)
            action = "created"

        await publish_event(
            nc,
            "maintenance.opened",
            {
                "window": window,
                "key": key,
                "bucket": MAINTENANCE_BUCKET,
                "action": action,
            },
        )
        return {
            "status": "opened",
            "action": action,
            "bucket": MAINTENANCE_BUCKET,
            "key": key,
            "window": window,
        }
    except Exception as exc:  # noqa: BLE001
        raise_recorded_nats_error(nc, exc)
    finally:
        await nc.drain()


async def close_window_async(
    nats_url: str,
    *,
    service_id: str,
    force: bool,
    closed_by_class: str,
    closed_by_id: str,
    credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    import nats.js.errors

    nc, js = await connect_jetstream(nats_url, credentials)
    try:
        kv = await get_bucket(js, create=False)
        if kv is None:
            return {
                "status": "no-op",
                "bucket": MAINTENANCE_BUCKET,
                "closed_count": 0,
                "windows": [],
            }

        if service_id == "all":
            active = await list_windows_async(nats_url, credentials)
            keys = sorted(active)
        else:
            keys = [maintenance_key(service_id)]

        closed_windows: list[dict[str, Any]] = []
        for key in keys:
            try:
                entry = await kv.get(key)
            except (nats.js.errors.KeyNotFoundError, nats.js.errors.KeyDeletedError):
                continue
            window = validate_maintenance_window(json.loads(entry.value.decode()), key)
            await kv.delete(key)
            closed_windows.append(window)

        if closed_windows:
            await publish_event(
                nc,
                "maintenance.force_closed" if force else "maintenance.closed",
                {
                    "bucket": MAINTENANCE_BUCKET,
                    "service_id": service_id,
                    "closed_by": {
                        "class": closed_by_class,
                        "id": closed_by_id,
                    },
                    "windows": closed_windows,
                    "force": force,
                },
            )
        return {
            "status": "closed" if closed_windows else "no-op",
            "bucket": MAINTENANCE_BUCKET,
            "closed_count": len(closed_windows),
            "windows": closed_windows,
            "force": force,
        }
    except Exception as exc:  # noqa: BLE001
        raise_recorded_nats_error(nc, exc)
    finally:
        await nc.drain()


def emit_mutation_audit_event(action: str, target: str, actor_class: str, actor_id: str) -> None:
    emit_event_best_effort(
        build_event(
            actor_class=actor_class,
            actor_id=actor_id,
            surface="nats",
            action=action,
            target=target,
            outcome="success",
            evidence_ref="docs/adr/0080-maintenance-window-and-change-suppression-protocol.md",
        ),
        context=action,
    )


def list_active_windows(context: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    if state_file_path() is not None:
        return load_local_state()
    context = context or load_controller_context()
    credentials = resolve_nats_credentials(context)
    with nats_tunnel(context) as local_port:
        return asyncio.run(list_windows_async(f"nats://127.0.0.1:{local_port}", credentials))


def list_active_windows_best_effort(
    context: dict[str, Any] | None = None,
    *,
    stderr: Any = sys.stderr,
) -> dict[str, dict[str, Any]]:
    try:
        return list_active_windows(context)
    except (ModuleNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Maintenance window warning: {exc}", file=stderr)
        return {}


def open_window(
    *,
    service_id: str,
    reason: str,
    duration_minutes: int,
    opened_by_class: str = DEFAULT_OPENED_BY_CLASS,
    opened_by_id: str = DEFAULT_OPENED_BY_ID,
    correlation_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    window = build_maintenance_window(
        service_id=service_id,
        reason=reason,
        duration_minutes=duration_minutes,
        opened_by_class=opened_by_class,
        opened_by_id=opened_by_id,
        correlation_id=correlation_id,
    )

    if state_file_path() is not None:
        state = load_local_state()
        state[maintenance_key(service_id)] = window
        save_local_state(state)
        result = {"status": "opened", "action": "created", "bucket": MAINTENANCE_BUCKET, "key": maintenance_key(service_id), "window": window}
    else:
        context = context or load_controller_context()
        credentials = resolve_nats_credentials(context)
        with nats_tunnel(context) as local_port:
            result = asyncio.run(open_window_async(f"nats://127.0.0.1:{local_port}", window, credentials))

    emit_mutation_audit_event("maintenance.open", service_id, opened_by_class, opened_by_id)
    return result


def close_window(
    *,
    service_id: str,
    force: bool = False,
    closed_by_class: str = DEFAULT_CLOSED_BY_CLASS,
    closed_by_id: str = DEFAULT_CLOSED_BY_ID,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    service_id = validate_service_id(service_id)
    closed_by_class = validate_opened_by_class(closed_by_class, "closed_by_class")
    closed_by_id = require_string(closed_by_id, "closed_by_id")

    if state_file_path() is not None:
        state = load_local_state()
        keys = [maintenance_key(service_id)] if service_id != "all" else sorted(state)
        windows = [state.pop(key) for key in keys if key in state]
        save_local_state(state)
        result = {
            "status": "closed" if windows else "no-op",
            "bucket": MAINTENANCE_BUCKET,
            "closed_count": len(windows),
            "windows": windows,
            "force": force,
        }
    else:
        context = context or load_controller_context()
        credentials = resolve_nats_credentials(context)
        with nats_tunnel(context) as local_port:
            result = asyncio.run(
                close_window_async(
                    f"nats://127.0.0.1:{local_port}",
                    service_id=service_id,
                    force=force,
                    closed_by_class=closed_by_class,
                    closed_by_id=closed_by_id,
                    credentials=credentials,
                )
            )

    emit_mutation_audit_event(
        "maintenance.force_close" if force else "maintenance.close",
        service_id,
        closed_by_class,
        closed_by_id,
    )
    return result


def ensure_bucket(context: dict[str, Any] | None = None) -> dict[str, Any]:
    if state_file_path() is not None:
        if not state_file_path().exists():
            save_local_state({})
        return {"status": "ready", "bucket": MAINTENANCE_BUCKET}
    context = context or load_controller_context()
    credentials = resolve_nats_credentials(context)
    with nats_tunnel(context) as local_port:
        return asyncio.run(ensure_bucket_async(f"nats://127.0.0.1:{local_port}", credentials))


def is_problem_detail(check: str, detail: dict[str, Any]) -> bool:
    if check in UNSUPPRESSIBLE_FINDING_CHECKS:
        return False
    if "ok" in detail:
        return detail["ok"] is False
    status = detail.get("status")
    if status is None:
        return True
    return status not in NON_PROBLEM_DETAIL_STATUSES


def matching_windows_for_finding(
    finding: dict[str, Any],
    active_windows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if finding.get("severity") in {"ok", "suppressed"}:
        return []
    if finding.get("check") in UNSUPPRESSIBLE_FINDING_CHECKS:
        return []

    all_window = active_windows.get(maintenance_key("all"))
    if all_window is not None:
        return [all_window]

    service_ids: set[str] = set()
    for detail in finding.get("details", []):
        detail = require_mapping(detail, "finding.details[]")
        if not is_problem_detail(finding["check"], detail):
            continue
        service_id = detail.get("service_id") or detail.get("owner_service")
        if service_id:
            service_ids.add(service_id)

    if not service_ids:
        return []

    windows = []
    for service_id in sorted(service_ids):
        window = active_windows.get(maintenance_key(service_id))
        if window is None:
            return []
        windows.append(window)
    return windows


def suppress_finding_for_maintenance(
    finding: dict[str, Any],
    active_windows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    finding = dict(finding)
    windows = matching_windows_for_finding(finding, active_windows)
    if not windows:
        return finding

    finding["original_severity"] = finding["severity"]
    finding["severity"] = "suppressed"
    finding["suppressed"] = True
    finding["summary"] = f"Suppressed during planned maintenance: {finding['summary']}"
    finding["maintenance_windows"] = [
        {
            "window_id": window["window_id"],
            "service_id": window["service_id"],
            "reason": window["reason"],
            "auto_close_at": window["auto_close_at"],
        }
        for window in windows
    ]
    return finding


def suppress_findings_for_maintenance(
    findings: list[dict[str, Any]],
    active_windows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [suppress_finding_for_maintenance(finding, active_windows) for finding in findings]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage NATS-backed maintenance windows for ADR 0080.")
    subparsers = parser.add_subparsers(dest="command")

    ensure_bucket_parser = subparsers.add_parser("ensure-bucket")
    ensure_bucket_parser.set_defaults(func=command_ensure_bucket)

    list_parser = subparsers.add_parser("list")
    list_parser.set_defaults(func=command_list)

    open_parser = subparsers.add_parser("open")
    open_parser.add_argument("--service", required=True)
    open_parser.add_argument("--reason", required=True)
    open_parser.add_argument("--duration-minutes", type=int, required=True)
    open_parser.add_argument("--opened-by-class", default=DEFAULT_OPENED_BY_CLASS)
    open_parser.add_argument("--opened-by-id", default=DEFAULT_OPENED_BY_ID)
    open_parser.add_argument("--correlation-id")
    open_parser.set_defaults(func=command_open)

    close_parser = subparsers.add_parser("close")
    close_parser.add_argument("--service", required=True)
    close_parser.add_argument("--force", action="store_true")
    close_parser.add_argument("--closed-by-class", default=DEFAULT_CLOSED_BY_CLASS)
    close_parser.add_argument("--closed-by-id", default=DEFAULT_CLOSED_BY_ID)
    close_parser.set_defaults(func=command_close)

    return parser


def command_ensure_bucket(_args: argparse.Namespace) -> int:
    print(json.dumps(ensure_bucket(), indent=2, sort_keys=True))
    return 0


def command_list(_args: argparse.Namespace) -> int:
    windows = list_active_windows()
    payload = {
        "bucket": MAINTENANCE_BUCKET,
        "count": len(windows),
        "windows": [windows[key] for key in sorted(windows)],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_open(args: argparse.Namespace) -> int:
    payload = open_window(
        service_id=args.service,
        reason=args.reason,
        duration_minutes=args.duration_minutes,
        opened_by_class=args.opened_by_class,
        opened_by_id=args.opened_by_id,
        correlation_id=args.correlation_id,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_close(args: argparse.Namespace) -> int:
    payload = close_window(
        service_id=args.service,
        force=args.force,
        closed_by_class=args.closed_by_class,
        closed_by_id=args.closed_by_id,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except (ModuleNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        return emit_cli_error("Maintenance window", exc, exit_code=1)


if __name__ == "__main__":
    sys.exit(main())
