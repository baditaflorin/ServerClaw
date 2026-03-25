#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import json
import os
import shlex
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json, load_yaml, repo_path
from platform.events import build_envelope
from platform.retry import async_with_retry, policy_for_surface


HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
GROUP_VARS_PATH = repo_path("inventory", "group_vars", "all.yml")
SECRET_MANIFEST_PATH = repo_path("config", "controller-local-secrets.json")
WORKSTREAMS_PATH = repo_path("workstreams.yaml")
NATS_PUBLISH_POLICY = policy_for_surface("nats_publish")


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


DRIFT_EVENT_TOPICS = {
    "warn": "platform.drift.warn",
    "critical": "platform.drift.critical",
    "unreachable": "platform.drift.unreachable",
}


def drift_event_topic(severity: str) -> str:
    normalized = str(severity).strip().lower()
    if normalized == "warning":
        normalized = "warn"
    if normalized not in DRIFT_EVENT_TOPICS:
        raise ValueError(f"unsupported drift severity '{severity}'")
    return DRIFT_EVENT_TOPICS[normalized]


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


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


def run_command(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandResult(
        argv=command,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def run_shell(command: str, *, cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult:
    return run_command(["/bin/bash", "-lc", command], cwd=cwd, env=env)


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
        remote_command,
    ]


def build_guest_ssh_tunnel_command(
    context: dict[str, Any],
    target: str,
    *,
    local_bind: str,
    remote_bind: str,
) -> list[str]:
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
        "-o",
        "ExitOnForwardFailure=yes",
        "-N",
        "-L",
        f"{local_bind}:{remote_bind}",
        f"{context['host_user']}@{guest_ip}",
    ]


def normalize_image_reference(reference: str) -> str:
    normalized = reference.strip()
    for prefix in ("docker.io/", "index.docker.io/"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
            break
    if normalized.startswith("library/"):
        normalized = normalized.removeprefix("library/")
    return normalized


def load_workstreams() -> list[dict[str, Any]]:
    payload = load_yaml(WORKSTREAMS_PATH)
    workstreams = payload.get("workstreams")
    if not isinstance(workstreams, list):
        raise ValueError("workstreams.yaml must define a workstreams list")
    return workstreams


def workstream_suppression(shared_surfaces: list[str]) -> tuple[bool, list[str]]:
    if not shared_surfaces:
        return False, []
    surfaces = {surface for surface in shared_surfaces if surface}
    matches: list[str] = []
    for workstream in load_workstreams():
        if workstream.get("status") != "in_progress":
            continue
        candidate_surfaces = {
            str(surface)
            for surface in workstream.get("shared_surfaces", [])
            if isinstance(surface, str) and surface
        }
        if surfaces.intersection(candidate_surfaces):
            matches.append(str(workstream.get("id", "")))
    return bool(matches), matches


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
            return {"user": "jetstream-admin", "password": password_path.read_text().strip()}
    return {}


def reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def wait_for_tunnel(process: subprocess.Popen[str], port: int) -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise RuntimeError(f"SSH tunnel failed: {(stderr or stdout).strip()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for SSH tunnel on localhost:{port}")


@contextmanager
def nats_tunnel(context: dict[str, Any]) -> int:
    local_port = reserve_local_port()
    command = build_guest_ssh_tunnel_command(
        context,
        "docker-runtime-lv3",
        local_bind=f"127.0.0.1:{local_port}",
        remote_bind="127.0.0.1:4222",
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


async def connect_nats(nats_url: str, credentials: dict[str, str] | None = None) -> Any:
    from nats.aio.client import Client as NATS

    nc = NATS()
    kwargs: dict[str, Any] = {
        "servers": [nats_url],
        "connect_timeout": 5,
        "allow_reconnect": False,
        "max_reconnect_attempts": 0,
        "reconnect_time_wait": 0,
    }
    if credentials:
        kwargs.update(credentials)
    await async_with_retry(
        lambda: nc.connect(**kwargs),
        policy=NATS_PUBLISH_POLICY,
        error_context=f"nats connect {nats_url}",
    )
    return nc


async def publish_nats_events_async(
    records: list[dict[str, Any]],
    *,
    nats_url: str,
    credentials: dict[str, str] | None = None,
) -> None:
    nc = await connect_nats(nats_url, credentials)
    try:
        for record in records:
            subject = str(record.get("subject") or record.get("event") or "").strip()
            if not subject:
                raise ValueError("NATS record must define subject or event")
            payload = record.get("payload")
            if not isinstance(payload, dict):
                payload = dict(record)
                payload.pop("subject", None)
                payload.pop("actor_id", None)
                payload.pop("context_id", None)
                payload.pop("ts", None)
            envelope = build_envelope(
                subject,
                payload,
                actor_id=str(record.get("actor_id") or "").strip() or None,
                context_id=str(record.get("context_id") or "").strip() or None,
                ts=record.get("ts") or record.get("generated_at") or record.get("occurred_at") or record.get("collected_at"),
            )
            await async_with_retry(
                lambda subject=subject, envelope=envelope: nc.publish(
                    subject,
                    json.dumps(envelope, separators=(",", ":")).encode(),
                ),
                policy=NATS_PUBLISH_POLICY,
                error_context=f"nats publish {subject}",
            )
        await async_with_retry(
            lambda: nc.flush(timeout=5),
            policy=NATS_PUBLISH_POLICY,
            error_context="nats flush",
        )
    finally:
        await nc.drain()


def publish_nats_events(
    records: list[dict[str, Any]],
    *,
    nats_url: str,
    credentials: dict[str, str] | None = None,
) -> None:
    if not records:
        return
    asyncio.run(publish_nats_events_async(records, nats_url=nats_url, credentials=credentials))
