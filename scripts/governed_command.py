#!/usr/bin/env python3
"""Controller-side entrypoint for governed command execution."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from command_catalog import (
    ALLOWED_IDENTITY_CLASSES,
    evaluate_approval,
    load_command_catalog,
    validate_command_catalog,
)
from controller_automation_toolkit import (
    REPO_ROOT,
    emit_cli_error,
    load_json,
    load_yaml,
    repo_path,
    resolve_repo_local_path,
)
from workflow_catalog import (
    load_secret_manifest,
    load_workflow_catalog,
    validate_secret_manifest,
    validate_workflow_catalog,
)


SECRET_ENV_BINDINGS = {
    "bootstrap_ssh_private_key": "BOOTSTRAP_KEY",
    "nats_jetstream_admin_password": "LV3_NATS_PASSWORD_FILE",
}
HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
GROUP_VARS_PATH = repo_path("inventory", "group_vars", "all.yml")
SECRET_MANIFEST_PATH = repo_path("config", "controller-local-secrets.json")


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def normalize_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_catalog_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    secret_manifest = load_secret_manifest()
    validate_secret_manifest(secret_manifest)
    workflow_catalog = load_workflow_catalog()
    validate_workflow_catalog(workflow_catalog, secret_manifest)
    command_catalog = load_command_catalog()
    validate_command_catalog(command_catalog, workflow_catalog, secret_manifest)
    return secret_manifest, workflow_catalog, command_catalog


def load_controller_context() -> dict[str, Any]:
    host_vars = load_yaml(HOST_VARS_PATH)
    group_vars = load_yaml(GROUP_VARS_PATH)
    secret_manifest = load_json(SECRET_MANIFEST_PATH)
    bootstrap_key = resolve_repo_local_path(secret_manifest["secrets"]["bootstrap_ssh_private_key"]["path"])
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
        f"ssh -i {shlex.quote(key_path)} -o IdentitiesOnly=yes -o BatchMode=yes "
        f"-o ConnectTimeout=10 -o LogLevel=ERROR -o StrictHostKeyChecking=no "
        f"-o UserKnownHostsFile=/dev/null {shlex.quote(host_login)} -W %h:%p"
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


def normalize_approver_classes(values: list[str]) -> list[str]:
    normalized = [require_str(value, f"approver_classes[{index}]") for index, value in enumerate(values)]
    for value in normalized:
        if value not in ALLOWED_IDENTITY_CLASSES:
            raise ValueError(f"approver class must be one of {sorted(ALLOWED_IDENTITY_CLASSES)}")
    return normalized


def validate_operator_parameters(contract: dict[str, Any], provided: dict[str, Any]) -> dict[str, str]:
    allowed_inputs = {
        item["name"]: item
        for item in contract["inputs"]
        if item["kind"] == "operator_parameter"
    }
    extras = sorted(set(provided) - set(allowed_inputs))
    if extras:
        raise ValueError(f"unsupported operator parameters for {contract['workflow_id']}: {', '.join(extras)}")
    missing = sorted(
        name
        for name, item in allowed_inputs.items()
        if item["required"] and name not in provided
    )
    if missing:
        raise ValueError(f"missing required operator parameters: {', '.join(missing)}")
    return {name: normalize_scalar(value) for name, value in provided.items()}


def runtime_repo_local_path(controller_secret_path: str | Path, runtime_repo_root: Path) -> Path:
    path = Path(controller_secret_path).expanduser()
    marker = ".local"
    if marker not in path.parts:
        raise ValueError(f"controller secret path is outside repo-local storage: {path}")
    marker_index = path.parts.index(marker)
    return runtime_repo_root.joinpath(*path.parts[marker_index:])


def build_secret_materialization(
    contract: dict[str, Any],
    secret_manifest: dict[str, Any],
    runtime_repo_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    staged_files: list[dict[str, Any]] = []
    env: dict[str, str] = {}
    for item in contract["inputs"]:
        if item["kind"] != "controller_secret":
            continue
        secret_id = item["name"]
        secret = require_mapping(secret_manifest["secrets"].get(secret_id), f"secrets.{secret_id}")
        secret_kind = require_str(secret.get("kind"), f"secrets.{secret_id}.kind")
        if secret_kind == "file":
            controller_path = resolve_repo_local_path(secret["path"])
            if not controller_path.exists():
                raise ValueError(f"controller secret file is missing: {controller_path}")
            runtime_path = runtime_repo_local_path(controller_path, runtime_repo_root)
            staged_files.append(
                {
                    "path": str(runtime_path),
                    "content_b64": base64.b64encode(controller_path.read_bytes()).decode("utf-8"),
                    "mode": "0600",
                }
            )
            env_name = SECRET_ENV_BINDINGS.get(secret_id)
            if env_name:
                env[env_name] = str(runtime_path)
            continue
        if secret_kind == "env":
            env_name = require_str(secret.get("name"), f"secrets.{secret_id}.name")
            env_value = os.environ.get(env_name, "").strip()
            if item["required"] and not env_value:
                raise ValueError(f"required controller environment secret is unset: {env_name}")
            if env_value:
                env[env_name] = env_value
            continue
        raise ValueError(f"unsupported controller secret kind for execution: {secret_kind}")
    return staged_files, env


def build_execution_payload(
    *,
    command_id: str,
    contract: dict[str, Any],
    workflow: dict[str, Any],
    command_catalog: dict[str, Any],
    secret_manifest: dict[str, Any],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    execution = contract["execution"]
    profile = command_catalog["execution_profiles"][execution["profile"]]
    runtime_repo_root = Path(profile["runtime_repo_root"])
    operator_parameters = validate_operator_parameters(contract, parameters)
    staged_files, env = build_secret_materialization(contract, secret_manifest, runtime_repo_root)
    env.update(operator_parameters)
    env.setdefault("ANSIBLE_HOST_KEY_CHECKING", "False")
    env.setdefault("MAKEFLAGS", "--no-print-directory")
    target = require_str(
        workflow["preferred_entrypoint"]["target"],
        "workflow.preferred_entrypoint.target",
    )
    unit_suffix = uuid.uuid4().hex[:12]
    payload = {
        "command_id": command_id,
        "runtime_host": profile["runtime_host"],
        "runtime_repo_root": profile["runtime_repo_root"],
        "runtime_compat_repo_root": profile["runtime_compat_repo_root"],
        "effective_user": profile["effective_user"],
        "working_directory": profile["working_directory"],
        "timeout_seconds": execution["timeout_seconds"],
        "kill_mode": profile["kill_mode"],
        "log_directory": profile["log_directory"],
        "receipt_directory": profile["receipt_directory"],
        "unit_name": f"lv3-governed-{command_id}-{unit_suffix}".replace("_", "-"),
        "command": ["make", target],
        "env": env,
        "staged_files": staged_files,
    }
    return payload


def submit_remote_payload(controller_context: dict[str, Any], runtime_host: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    payload_base64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    remote_repo_root = shlex.quote(payload["runtime_repo_root"])
    remote_payload = shlex.quote(payload_base64)
    remote_command = (
        f"sudo python3 {remote_repo_root}/scripts/governed_command_runtime.py "
        f"submit --payload-base64 {remote_payload}"
    )
    if runtime_host == "docker-runtime-lv3":
        command = build_guest_ssh_command(controller_context, runtime_host, remote_command)
    elif runtime_host == controller_context["host_vars"]["host_public_hostname"]:
        command = build_host_ssh_command(controller_context, remote_command)
    elif runtime_host == "proxmox_florin":
        command = build_host_ssh_command(controller_context, remote_command)
    else:
        command = build_guest_ssh_command(controller_context, runtime_host, remote_command)
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError(completed.stderr.strip() or "remote governed command returned no output")
    return require_mapping(json.loads(stdout), "remote runtime result"), completed.returncode


def execute_governed_command(
    *,
    command_id: str,
    requester_class: str,
    approver_classes: list[str],
    preflight_passed: bool,
    validation_passed: bool,
    receipt_planned: bool,
    self_approve: bool,
    break_glass: bool,
    parameters: dict[str, Any] | None = None,
    dry_run: bool = True,
) -> tuple[dict[str, Any], str]:
    secret_manifest, workflow_catalog, command_catalog = load_catalog_context()
    contract = command_catalog["commands"].get(command_id)
    if contract is None:
        raise ValueError(f"unknown command '{command_id}'")
    workflow = workflow_catalog["workflows"][contract["workflow_id"]]
    verdict = evaluate_approval(
        command_catalog,
        workflow_catalog,
        command_id,
        requester_class,
        normalize_approver_classes(approver_classes),
        preflight_passed=preflight_passed,
        validation_passed=validation_passed,
        receipt_planned=receipt_planned,
        self_approve=self_approve,
        break_glass=break_glass,
    )
    if not verdict["approved"]:
        return (
            {
                "approved": False,
                "executed": False,
                "command_id": command_id,
                "workflow_id": verdict["workflow_id"],
                "entrypoint": verdict["entrypoint"],
                "reasons": verdict["reasons"],
            },
            "rejected",
        )

    payload = build_execution_payload(
        command_id=command_id,
        contract=contract,
        workflow=workflow,
        command_catalog=command_catalog,
        secret_manifest=secret_manifest,
        parameters=parameters or {},
    )
    response = {
        "approved": True,
        "executed": False,
        "command_id": command_id,
        "workflow_id": verdict["workflow_id"],
        "entrypoint": verdict["entrypoint"],
        "reasons": [],
        "runtime_host": payload["runtime_host"],
        "unit_name": payload["unit_name"],
        "stdout_log": str(Path(payload["log_directory"]) / f"{payload['unit_name']}.stdout.log"),
        "stderr_log": str(Path(payload["log_directory"]) / f"{payload['unit_name']}.stderr.log"),
        "receipt_path": str(Path(payload["receipt_directory"]) / f"{payload['unit_name']}.json"),
        "parameters": require_mapping(parameters or {}, "parameters"),
    }
    if dry_run:
        return response, "success"

    controller_context = load_controller_context()
    runtime_result, remote_returncode = submit_remote_payload(
        controller_context,
        payload["runtime_host"],
        payload,
    )
    response.update(
        {
            "executed": runtime_result.get("returncode", remote_returncode) == 0,
            "returncode": runtime_result.get("returncode", remote_returncode),
            "stdout_log": runtime_result.get("stdout_log", response["stdout_log"]),
            "stderr_log": runtime_result.get("stderr_log", response["stderr_log"]),
            "receipt_path": runtime_result.get("receipt_path", response["receipt_path"]),
            "runtime_host": runtime_result.get("runtime_host", response["runtime_host"]),
            "unit_name": runtime_result.get("unit_name", response["unit_name"]),
        }
    )
    if runtime_result.get("status") != "ok":
        response["reasons"] = [runtime_result.get("error") or runtime_result.get("stderr") or "governed command failed"]
    outcome = "success" if response["executed"] else "failure"
    return response, outcome


def parse_key_value_pairs(values: list[str]) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    for index, value in enumerate(values):
        if "=" not in value:
            raise ValueError(f"--param[{index}] must use NAME=VALUE")
        key, raw_value = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--param[{index}] must use a non-empty NAME")
        parameters[key] = raw_value
    return parameters


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one governed command through the bounded systemd-run envelope.")
    parser.add_argument("--command", required=True)
    parser.add_argument("--requester-class", required=True)
    parser.add_argument("--approver-classes", action="append", default=[])
    parser.add_argument("--preflight-passed", action="store_true")
    parser.add_argument("--validation-passed", action="store_true")
    parser.add_argument("--receipt-planned", action="store_true")
    parser.add_argument("--self-approve", action="store_true")
    parser.add_argument("--break-glass", action="store_true")
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result, _outcome = execute_governed_command(
            command_id=require_str(args.command, "--command"),
            requester_class=require_str(args.requester_class, "--requester-class"),
            approver_classes=args.approver_classes,
            preflight_passed=args.preflight_passed,
            validation_passed=args.validation_passed,
            receipt_planned=args.receipt_planned,
            self_approve=args.self_approve,
            break_glass=args.break_glass,
            parameters=parse_key_value_pairs(args.param),
            dry_run=args.dry_run,
        )
    except Exception as exc:
        return emit_cli_error("Governed command", exc)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("executed", False) or result.get("approved", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
