from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any

from platform.repo import load_json, load_yaml, resolve_repo_local_path, write_json


MAINTENANCE_BUCKET = "maintenance-windows"
MAINTENANCE_BUCKET_MAX_AGE_SECONDS = 2 * 60 * 60
MAINTENANCE_KEY_PREFIX = "maintenance/"
MAINTENANCE_STATE_FILE_ENV = "LV3_MAINTENANCE_WINDOWS_FILE"
MAINTENANCE_NATS_URL_ENV = "LV3_MAINTENANCE_WINDOWS_NATS_URL"
SERVICE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
ALLOWED_OPENED_BY_CLASSES = {"operator", "agent"}


def _repo_path(repo_root: Path | None, *parts: str) -> Path:
    base = Path(__file__).resolve().parents[2] if repo_root is None else Path(repo_root)
    return base.joinpath(*parts)


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


def load_controller_context(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2] if repo_root is None else Path(repo_root)
    host_vars_path = _repo_path(repo_root, "inventory", "host_vars", "proxmox-host.yml")
    group_vars_path = _repo_path(repo_root, "inventory", "group_vars", "all.yml")
    secret_manifest_path = _repo_path(repo_root, "config", "controller-local-secrets.json")
    host_vars = load_yaml(host_vars_path)
    group_vars = load_yaml(group_vars_path)
    secret_manifest = load_json(secret_manifest_path)
    bootstrap_key = resolve_repo_local_path(
        secret_manifest["secrets"]["bootstrap_ssh_private_key"]["path"],
        repo_root=root,
    )
    guests = {guest["name"]: guest["ipv4"] for guest in host_vars["proxmox_guests"]}
    return {
        "repo_root": root,
        "host_vars": host_vars,
        "group_vars": group_vars,
        "secret_manifest": secret_manifest,
        "bootstrap_key": bootstrap_key,
        "host_user": group_vars["proxmox_host_admin_user"],
        "host_addr": host_vars["management_tailscale_ipv4"],
        "guests": guests,
    }


def resolve_nats_credentials(context: dict[str, Any] | None = None) -> dict[str, str]:
    env_user = os.environ.get("LV3_NATS_USERNAME", "").strip()
    env_password = os.environ.get("LV3_NATS_PASSWORD", "").strip()
    env_password_file = os.environ.get("LV3_NATS_PASSWORD_FILE", "").strip()
    if env_password_file and not env_password:
        env_password = Path(env_password_file).expanduser().read_text().strip()
    if env_user and env_password:
        return {"user": env_user, "password": env_password}

    context = context or {}
    secret_manifest = context.get("secret_manifest", {})
    secret_entry = secret_manifest.get("secrets", {}).get("nats_jetstream_admin_password")
    if isinstance(secret_entry, dict) and secret_entry.get("kind") == "file":
        password_path = resolve_repo_local_path(
            secret_entry["path"],
            repo_root=Path(context.get("repo_root") or Path(__file__).resolve().parents[2]),
        )
        if password_path.exists():
            return {"user": "jetstream-admin", "password": password_path.read_text().strip()}
    return {}


def direct_nats_url() -> str:
    return os.environ.get(MAINTENANCE_NATS_URL_ENV, "").strip() or os.environ.get("LV3_NATS_URL", "").strip()


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
        "docker-runtime",
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


@contextmanager
def maintenance_nats_connection(
    context: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
):
    credentials = resolve_nats_credentials(context)
    direct_url = direct_nats_url()
    if direct_url:
        yield direct_url, credentials
        return

    resolved_context = context or load_controller_context(repo_root=repo_root)
    credentials = resolve_nats_credentials(resolved_context)
    with nats_tunnel(resolved_context) as local_port:
        yield f"nats://127.0.0.1:{local_port}", credentials


def maintenance_key(service_id: str) -> str:
    return f"{MAINTENANCE_KEY_PREFIX}{service_id}"


def validate_opened_by_class(value: str, path: str) -> str:
    value = require_string(value, path)
    if value not in ALLOWED_OPENED_BY_CLASSES:
        raise ValueError(f"{path} must be one of {sorted(ALLOWED_OPENED_BY_CLASSES)}")
    return value


def validate_service_id(service_id: str, path: str = "service_id") -> str:
    service_id = require_string(service_id, path)
    if service_id == "all":
        return service_id
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
    alertmanager_silence_id = window.get("alertmanager_silence_id")
    if alertmanager_silence_id is not None:
        require_string(alertmanager_silence_id, f"{path}.alertmanager_silence_id")
    return window


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


def list_active_windows(
    context: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    if state_file_path() is not None:
        return load_local_state()
    with maintenance_nats_connection(context, repo_root=repo_root) as (nats_url, credentials):
        return asyncio.run(list_windows_async(nats_url, credentials))


def list_active_windows_best_effort(
    context: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
    stderr: Any = sys.stderr,
) -> dict[str, dict[str, Any]]:
    try:
        return list_active_windows(context, repo_root=repo_root)
    except (ModuleNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Maintenance window warning: {exc}", file=stderr)
        return {}
