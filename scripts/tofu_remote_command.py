#!/usr/bin/env python3
"""Build remote-safe OpenTofu command lines with controller-local auth."""

from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path

from environment_catalog import environment_choices
from session_workspace import resolve_session_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SECRET_MANIFEST = REPO_ROOT / "config" / "controller-local-secrets.json"
BUILD_SERVER_CONFIG = REPO_ROOT / "config" / "build-server.json"
DEFAULT_NODE_NAME = "proxmox-host"

PRODUCTION_VMIDS = {
    "nginx": 110,
    "docker-runtime": 120,
    "docker-build": 130,
    "monitoring": 140,
    "postgres": 150,
    "backup": 160,
}

STAGING_VMIDS = {
    "docker-runtime-staging": 220,
    "monitoring-staging": 240,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "apply", "drift", "import"])
    parser.add_argument("environment", choices=environment_choices())
    parser.add_argument("--vm", help="VM name for import operations.")
    parser.add_argument(
        "--token-file",
        type=Path,
        help="Controller-local Proxmox API token payload.",
    )
    return parser.parse_args()


def default_token_file() -> Path:
    manifest = json.loads(DEFAULT_SECRET_MANIFEST.read_text(encoding="utf-8"))
    return Path(manifest["secrets"]["proxmox_api_token_payload"]["path"])


def build_server_workspace() -> str:
    session_workspace = os.environ.get("LV3_REMOTE_WORKSPACE_ROOT")
    if session_workspace:
        return session_workspace
    config = json.loads(BUILD_SERVER_CONFIG.read_text(encoding="utf-8"))
    workspace = resolve_session_workspace(
        repo_root=REPO_ROOT,
        remote_workspace_base=Path(str(config["workspace_root"])),
    )
    return workspace.remote_workspace_root or str(config["workspace_root"])


def read_token_payload(token_file: Path | None) -> tuple[str, str]:
    resolved = token_file or default_token_file()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    endpoint = payload["api_url"]
    api_token = f"{payload['full_token_id']}={payload['value']}"
    return endpoint, api_token


def module_label(vm_name: str) -> str:
    return vm_name.replace("-", "_")


def import_target(environment: str, vm_name: str) -> tuple[str, str]:
    if environment == "production":
        if vm_name not in PRODUCTION_VMIDS:
            raise SystemExit(f"unknown production VM: {vm_name}")
        vmid = PRODUCTION_VMIDS[vm_name]
    else:
        if vm_name not in STAGING_VMIDS:
            raise SystemExit(f"unknown staging VM: {vm_name}")
        vmid = STAGING_VMIDS[vm_name]

    address = f"module.{module_label(vm_name)}.proxmox_virtual_environment_vm.this"
    import_id = f"{DEFAULT_NODE_NAME}/{vmid}"
    return address, import_id


def main() -> None:
    args = parse_args()
    endpoint, api_token = read_token_payload(args.token_file)

    command_prefix = [
        "TOFU_DOCKER_NETWORK=host",
        f"TF_VAR_proxmox_endpoint={shlex.quote(endpoint)}",
        f"TF_VAR_proxmox_api_token={shlex.quote(api_token)}",
    ]

    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_DEFAULT_REGION",
        "AWS_REGION",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_S3",
    ):
        value = os.environ.get(name)
        if value:
            command_prefix.append(f"{name}={shlex.quote(value)}")

    if args.action == "import":
        if not args.vm:
            raise SystemExit("--vm is required for import")
        address, import_id = import_target(args.environment, args.vm)
        command = (
            [
                "cd",
                build_server_workspace(),
                "&&",
            ]
            + command_prefix
            + [
                "./scripts/tofu_exec.sh",
                "import",
                args.environment,
                address,
                import_id,
            ]
        )
    else:
        command = (
            [
                "cd",
                build_server_workspace(),
                "&&",
            ]
            + command_prefix
            + ["./scripts/tofu_exec.sh", args.action, args.environment]
        )

    print(" ".join(command))


if __name__ == "__main__":
    main()
