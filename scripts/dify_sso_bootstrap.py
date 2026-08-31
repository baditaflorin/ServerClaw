#!/usr/bin/env python3
# Purpose: Idempotently bootstrap Dify and reconcile workspace SSO with an Authentik OIDC provider.
# Use case: Called by the dify_runtime Ansible role after the stack is running.
# Inputs: Dify/admin/init credentials, Authentik OIDC settings, and optional SSH tunnel coordinates.
# Outputs: JSON summary of admin setup, SSO action, change state, and transport.
# Idempotency: Skips completed admin setup and matching SSO state; the SSH forward is transient.

from __future__ import annotations

import argparse
import json
import shlex
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dify_api import DifyClient, DifyApiError, read_secret

_PROTOCOL = "oidc"
_SSH_CONNECT_TIMEOUT_SECONDS = 10
_SSH_TUNNEL_READY_TIMEOUT_SECONDS = 10
_SSH_TUNNEL_SHUTDOWN_TIMEOUT_SECONDS = 3


def _sso_matches(current: dict, client_id: str, issuer_url: str) -> bool:
    """Return True when the live SSO config already matches the desired state."""
    return (
        current.get("enabled") is True
        and current.get("type") == _PROTOCOL
        and current.get("client_id") == client_id
        and current.get("issuer_url") == issuer_url
    )


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _build_ssh_tunnel_command(
    *,
    ssh_host: str,
    ssh_user: str,
    ssh_jump_host: str,
    ssh_jump_user: str,
    ssh_jump_port: int,
    ssh_private_key_file: str,
    ssh_remote_port: int,
    local_port: int,
) -> list[str]:
    common_options = [
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={_SSH_CONNECT_TIMEOUT_SECONDS}",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    jump_command = [
        "ssh",
        "-i",
        ssh_private_key_file,
        *common_options,
        "-p",
        str(ssh_jump_port),
        "-W",
        "%h:%p",
        f"{ssh_jump_user}@{ssh_jump_host}",
    ]
    return [
        "ssh",
        "-i",
        ssh_private_key_file,
        *common_options,
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        f"ProxyCommand={shlex.join(jump_command)}",
        "-N",
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:{ssh_remote_port}",
        f"{ssh_user}@{ssh_host}",
    ]


def _wait_for_ssh_tunnel(process: subprocess.Popen[str], local_port: int) -> None:
    deadline = time.monotonic() + _SSH_TUNNEL_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            detail = (stderr or stdout).strip()
            raise RuntimeError(f"Dify SSH tunnel exited before becoming ready: {detail}")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Dify SSH tunnel did not become ready before the timeout")


@contextmanager
def _dify_api_base_url(args: argparse.Namespace) -> Iterator[str]:
    tunnel_values = (
        args.ssh_host,
        args.ssh_user,
        args.ssh_jump_host,
        args.ssh_jump_user,
        args.ssh_private_key_file,
        args.ssh_remote_port,
    )
    if not any(value is not None for value in tunnel_values):
        yield args.base_url
        return
    if not all(value is not None for value in tunnel_values):
        raise ValueError("all Dify SSH tunnel arguments must be supplied together")

    private_key = Path(args.ssh_private_key_file).expanduser().resolve()
    if not private_key.is_file():
        raise FileNotFoundError("Dify SSH tunnel private key is missing")

    local_port = _reserve_local_port()
    command = _build_ssh_tunnel_command(
        ssh_host=args.ssh_host,
        ssh_user=args.ssh_user,
        ssh_jump_host=args.ssh_jump_host,
        ssh_jump_user=args.ssh_jump_user,
        ssh_jump_port=args.ssh_jump_port,
        ssh_private_key_file=str(private_key),
        ssh_remote_port=args.ssh_remote_port,
        local_port=local_port,
    )
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _wait_for_ssh_tunnel(process, local_port)
        yield f"http://127.0.0.1:{local_port}"
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=_SSH_TUNNEL_SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=_SSH_TUNNEL_SHUTDOWN_TIMEOUT_SECONDS)


def _bootstrap_sso(
    client: DifyClient,
    *,
    admin_email: str,
    admin_name: str,
    admin_password: str,
    init_password: str,
    authentik_client_id: str,
    authentik_client_secret: str,
    authentik_issuer_url: str,
) -> dict:
    setup_before = client.setup_status()
    setup_changed = setup_before.get("step") != "finished"
    client.setup(
        email=admin_email,
        name=admin_name[:30],
        password=admin_password,
        init_password=init_password,
    )
    client.login(email=admin_email, password=admin_password)

    current = client.get_sso_setting()
    if current is None:
        return {
            "action": "unavailable",
            "changed": setup_changed,
            "admin_bootstrap": "configured" if setup_changed else "already-configured",
            "reason": "SSO endpoint not present in this Dify version",
        }

    if _sso_matches(current, client_id=authentik_client_id, issuer_url=authentik_issuer_url):
        return {
            "action": "already-configured",
            "changed": setup_changed,
            "admin_bootstrap": "configured" if setup_changed else "already-configured",
            "type": _PROTOCOL,
            "client_id": authentik_client_id,
            "issuer_url": authentik_issuer_url,
        }

    try:
        response = client.configure_sso(
            enabled=True,
            protocol=_PROTOCOL,
            client_id=authentik_client_id,
            client_secret=authentik_client_secret,
            issuer_url=authentik_issuer_url,
        )
    except DifyApiError as exc:
        if "not support programmatic" in str(exc) or "not found" in str(exc).lower():
            return {
                "action": "unavailable",
                "changed": setup_changed,
                "admin_bootstrap": "configured" if setup_changed else "already-configured",
                "reason": str(exc),
            }
        raise

    return {
        "action": "configured",
        "changed": True,
        "admin_bootstrap": "configured" if setup_changed else "already-configured",
        "type": _PROTOCOL,
        "client_id": authentik_client_id,
        "issuer_url": authentik_issuer_url,
        "response": response,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Dify workspace SSO to use an Authentik OIDC provider.")
    parser.add_argument("--base-url", required=True, help="Public Dify base URL (e.g. https://agents.localhost)")
    parser.add_argument("--admin-email", required=True, help="Dify admin email used to log in")
    parser.add_argument("--admin-name", default="Platform Operator", help="Dify admin name used during first setup")
    parser.add_argument("--admin-password-file", required=True, help="Path to the Dify admin password file")
    parser.add_argument("--init-password-file", required=True, help="Path to the Dify init-validation password file")
    parser.add_argument("--authentik-client-id", required=True, help="Authentik client ID registered for Dify")
    parser.add_argument(
        "--authentik-client-secret-file", required=True, help="Path to the Authentik client secret file"
    )
    parser.add_argument(
        "--authentik-issuer-url",
        required=True,
        help="Authentik issuer URL (e.g. https://id.example.com/application/o/dify/)",
    )
    parser.add_argument("--ssh-host", help="Dify runtime SSH host for a loopback API tunnel")
    parser.add_argument("--ssh-user", help="Dify runtime SSH user")
    parser.add_argument("--ssh-jump-host", help="Public SSH jump host")
    parser.add_argument("--ssh-jump-user", help="Public SSH jump user")
    parser.add_argument("--ssh-jump-port", type=int, default=22, help="Public SSH jump port")
    parser.add_argument("--ssh-private-key-file", help="SSH private key used for the jump and runtime hosts")
    parser.add_argument("--ssh-remote-port", type=int, help="Dify runtime loopback port to forward")
    args = parser.parse_args()

    admin_password = read_secret(args.admin_password_file)
    init_password = read_secret(args.init_password_file)
    client_secret = read_secret(args.authentik_client_secret_file)
    if len(init_password) > 30:
        raise ValueError("Dify initialization password exceeds the live API maximum of 30 characters")

    with _dify_api_base_url(args) as base_url:
        result = _bootstrap_sso(
            DifyClient(base_url),
            admin_email=args.admin_email,
            admin_name=args.admin_name,
            admin_password=admin_password,
            init_password=init_password,
            authentik_client_id=args.authentik_client_id,
            authentik_client_secret=client_secret,
            authentik_issuer_url=args.authentik_issuer_url,
        )
    result["transport"] = "ssh_loopback_forward" if args.ssh_host else "direct"
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
