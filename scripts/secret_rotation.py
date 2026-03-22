#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, run_command
from workflow_catalog import load_secret_manifest, validate_secret_manifest


SECRET_CATALOG_PATH = repo_path("config", "secret-catalog.json")
SECRET_ROTATION_PLAYBOOK = repo_path("playbooks", "secret-rotation.yml")
ANSIBLE_INVENTORY = repo_path("inventory", "hosts.yml")
DEFAULT_BOOTSTRAP_KEY = repo_path(".local", "ssh", "hetzner_llm_agents_ed25519")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
ALLOWED_SECRET_TYPES = {
    "admin_password",
    "admin_token",
    "api_key",
    "database_password",
    "mailbox_password",
    "metrics_password",
}
ALLOWED_RISK_LEVELS = {"low", "high"}
ALLOWED_APPROVAL_MODES = {"auto", "approval_required"}
ALLOWED_GENERATORS = {"base64_24", "hex_32"}
ALLOWED_APPLY_TARGETS = {
    "mail_platform_profile_field",
    "mail_platform_runtime_field",
    "windmill_database",
    "windmill_superadmin",
}


def load_secret_catalog() -> dict:
    return load_json(SECRET_CATALOG_PATH)


def require_mapping(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_int(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def require_nullable_timestamp(value: Any, path: str) -> str | None:
    if value is None:
        return None
    value = require_str(value, path)
    parse_timestamp(value, path)
    return value


def parse_timestamp(value: str, path: str) -> dt.datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{path} must use ISO-8601 timestamp format") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def validate_secret_catalog(catalog: dict, secret_manifest: dict) -> None:
    if catalog.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"secret catalog must declare schema_version '{SUPPORTED_SCHEMA_VERSION}'"
        )

    metadata = require_mapping(catalog.get("metadata"), "metadata")
    require_str(metadata.get("state_source"), "metadata.state_source")
    require_str(metadata.get("value_field"), "metadata.value_field")
    require_str(metadata.get("last_rotated_metadata_key"), "metadata.last_rotated_metadata_key")
    require_str(metadata.get("rotated_by_metadata_key"), "metadata.rotated_by_metadata_key")
    require_str(metadata.get("default_event_subject"), "metadata.default_event_subject")
    require_str(metadata.get("default_glitchtip_component"), "metadata.default_glitchtip_component")

    secrets = require_mapping(catalog.get("secrets"), "secrets")
    if not secrets:
        raise ValueError("secrets must not be empty")

    secret_ids = set(secret_manifest["secrets"].keys())
    for secret_id, secret in secrets.items():
        secret = require_mapping(secret, f"secrets.{secret_id}")
        require_str(secret_id, f"secret id '{secret_id}'")
        require_str(secret.get("owner"), f"secrets.{secret_id}.owner")
        require_str(secret.get("service"), f"secrets.{secret_id}.service")

        secret_type = require_str(secret.get("secret_type"), f"secrets.{secret_id}.secret_type")
        if secret_type not in ALLOWED_SECRET_TYPES:
            raise ValueError(
                f"secrets.{secret_id}.secret_type must be one of {sorted(ALLOWED_SECRET_TYPES)}"
            )

        risk_level = require_str(secret.get("risk_level"), f"secrets.{secret_id}.risk_level")
        if risk_level not in ALLOWED_RISK_LEVELS:
            raise ValueError(
                f"secrets.{secret_id}.risk_level must be one of {sorted(ALLOWED_RISK_LEVELS)}"
            )

        approval_mode = require_str(secret.get("approval_mode"), f"secrets.{secret_id}.approval_mode")
        if approval_mode not in ALLOWED_APPROVAL_MODES:
            raise ValueError(
                f"secrets.{secret_id}.approval_mode must be one of {sorted(ALLOWED_APPROVAL_MODES)}"
            )
        if risk_level == "high" and approval_mode != "approval_required":
            raise ValueError(
                f"secrets.{secret_id}.approval_mode must be approval_required for high-risk secrets"
            )

        require_str(secret.get("command_contract"), f"secrets.{secret_id}.command_contract")
        period = require_int(secret.get("rotation_period_days"), f"secrets.{secret_id}.rotation_period_days", 1)
        warning = require_int(secret.get("warning_window_days"), f"secrets.{secret_id}.warning_window_days", 0)
        if warning >= period:
            raise ValueError(
                f"secrets.{secret_id}.warning_window_days must be smaller than rotation_period_days"
            )

        require_nullable_timestamp(secret.get("last_rotated"), f"secrets.{secret_id}.last_rotated")

        seed_secret_id = require_str(
            secret.get("seed_controller_secret_id"),
            f"secrets.{secret_id}.seed_controller_secret_id",
        )
        if seed_secret_id not in secret_ids:
            raise ValueError(
                f"secrets.{secret_id}.seed_controller_secret_id references unknown controller secret '{seed_secret_id}'"
            )

        generator = require_str(secret.get("value_generator"), f"secrets.{secret_id}.value_generator")
        if generator not in ALLOWED_GENERATORS:
            raise ValueError(
                f"secrets.{secret_id}.value_generator must be one of {sorted(ALLOWED_GENERATORS)}"
            )

        require_str(secret.get("openbao_path"), f"secrets.{secret_id}.openbao_path")
        require_str(secret.get("openbao_field"), f"secrets.{secret_id}.openbao_field")

        apply_target = require_str(secret.get("apply_target"), f"secrets.{secret_id}.apply_target")
        if apply_target not in ALLOWED_APPLY_TARGETS:
            raise ValueError(
                f"secrets.{secret_id}.apply_target must be one of {sorted(ALLOWED_APPLY_TARGETS)}"
            )

        apply_field = secret.get("apply_field")
        if apply_target in {"mail_platform_profile_field", "mail_platform_runtime_field"}:
            require_str(apply_field, f"secrets.{secret_id}.apply_field")
        elif apply_field is not None:
            require_str(apply_field, f"secrets.{secret_id}.apply_field")

        profile_id = secret.get("profile_id")
        if apply_target == "mail_platform_profile_field":
            require_str(profile_id, f"secrets.{secret_id}.profile_id")
        elif profile_id is not None:
            require_str(profile_id, f"secrets.{secret_id}.profile_id")

        compatibility_mirror = secret.get("compatibility_mirror")
        if compatibility_mirror is not None:
            compatibility_mirror = require_mapping(
                compatibility_mirror, f"secrets.{secret_id}.compatibility_mirror"
            )
            require_str(
                compatibility_mirror.get("openbao_path"),
                f"secrets.{secret_id}.compatibility_mirror.openbao_path",
            )
            require_str(
                compatibility_mirror.get("field"),
                f"secrets.{secret_id}.compatibility_mirror.field",
            )

        require_str(secret.get("event_subject"), f"secrets.{secret_id}.event_subject")
        require_str(secret.get("glitchtip_component"), f"secrets.{secret_id}.glitchtip_component")


def normalized_now(now: str | None = None) -> dt.datetime:
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    return parse_timestamp(now, "now")


def rotation_due(secret: dict, *, now: dt.datetime) -> bool:
    last_rotated = secret.get("last_rotated")
    if last_rotated is None:
        return True
    threshold = parse_timestamp(last_rotated, "last_rotated") + dt.timedelta(
        days=secret["rotation_period_days"] - secret["warning_window_days"]
    )
    return now >= threshold


def next_rotation_due(secret: dict) -> str | None:
    last_rotated = secret.get("last_rotated")
    if last_rotated is None:
        return None
    threshold = parse_timestamp(last_rotated, "last_rotated") + dt.timedelta(
        days=secret["rotation_period_days"] - secret["warning_window_days"]
    )
    return threshold.isoformat().replace("+00:00", "Z")


def build_playbook_command(
    secret_id: str,
    *,
    mode: str,
    force: bool,
    approve_high_risk: bool,
    new_value: str | None,
) -> tuple[list[str], dict[str, str]]:
    command = [
        "ansible-playbook",
        "-i",
        str(ANSIBLE_INVENTORY),
        str(SECRET_ROTATION_PLAYBOOK),
        "--private-key",
        str(Path(os.environ.get("BOOTSTRAP_KEY", str(DEFAULT_BOOTSTRAP_KEY)))),
        "-e",
        "proxmox_guest_ssh_connection_mode=proxmox_host_jump",
        "-e",
        f"secret_rotation_secret_id={secret_id}",
        "-e",
        f"secret_rotation_mode={mode}",
        "-e",
        f"secret_rotation_force={'true' if force else 'false'}",
        "-e",
        f"secret_rotation_allow_high_risk={'true' if approve_high_risk else 'false'}",
    ]
    if new_value is not None:
        command.extend(["-e", f"secret_rotation_new_value={new_value}"])
    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    return command, env


def build_rotation_event(
    secret_id: str,
    secret: dict,
    *,
    status: str,
    mode: str,
    command: list[str],
) -> dict:
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "event_type": "secret_rotation",
        "event_id": uuid.uuid4().hex,
        "subject": secret["event_subject"],
        "timestamp": timestamp,
        "status": status,
        "mode": mode,
        "secret_id": secret_id,
        "service": secret["service"],
        "owner": secret["owner"],
        "risk_level": secret["risk_level"],
        "approval_mode": secret["approval_mode"],
        "command_contract": secret["command_contract"],
        "playbook_command": command,
    }


def build_glitchtip_event(secret_id: str, secret: dict, rotation_event: dict, error: str) -> dict:
    return {
        "event_id": rotation_event["event_id"],
        "message": f"Secret rotation failed for {secret_id}",
        "level": "error",
        "platform": "python",
        "tags": {
            "component": secret["glitchtip_component"],
            "secret_id": secret_id,
            "service": secret["service"],
            "risk_level": secret["risk_level"],
        },
        "extra": {
            "rotation": rotation_event,
            "error": error,
        },
    }


def post_json(url: str, payload: dict) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15):
        return None


def maybe_emit_success(rotation_event: dict) -> None:
    nats_url = os.environ.get("SECRET_ROTATION_NATS_EVENT_URL")
    if nats_url:
        post_json(nats_url, {"subject": rotation_event["subject"], "payload": rotation_event})


def maybe_emit_failure(rotation_event: dict, glitchtip_event: dict) -> None:
    nats_url = os.environ.get("SECRET_ROTATION_NATS_EVENT_URL")
    if nats_url:
        post_json(nats_url, {"subject": rotation_event["subject"], "payload": rotation_event})

    glitchtip_url = os.environ.get("SECRET_ROTATION_GLITCHTIP_EVENT_URL")
    if glitchtip_url:
        post_json(glitchtip_url, glitchtip_event)


def list_catalog(catalog: dict, *, now: dt.datetime) -> int:
    print(f"Secret catalog: {SECRET_CATALOG_PATH}")
    print("Managed secrets:")
    for secret_id, secret in sorted(catalog["secrets"].items()):
        due = "due" if rotation_due(secret, now=now) else "scheduled"
        next_due = next_rotation_due(secret) or "initial rotation required"
        print(
            f"  - {secret_id} [{secret['risk_level']}, {secret['command_contract']}, {due}]"
            f" -> {next_due}"
        )
    return 0


def show_secret(secret_id: str, secret: dict, *, now: dt.datetime) -> int:
    print(f"Secret: {secret_id}")
    print(f"Service: {secret['service']}")
    print(f"Owner: {secret['owner']}")
    print(f"Risk level: {secret['risk_level']}")
    print(f"Approval mode: {secret['approval_mode']}")
    print(f"Command contract: {secret['command_contract']}")
    print(f"Rotation period (days): {secret['rotation_period_days']}")
    print(f"Warning window (days): {secret['warning_window_days']}")
    print(f"Last rotated: {secret.get('last_rotated') or 'not yet'}")
    print(f"Next due: {next_rotation_due(secret) or 'initial rotation required'}")
    print(f"Due now: {'yes' if rotation_due(secret, now=now) else 'no'}")
    print(f"OpenBao path: {secret['openbao_path']}")
    print(f"Apply target: {secret['apply_target']}")
    return 0


def run_rotation(secret_id: str, secret: dict, *, mode: str, force: bool, approve_high_risk: bool, new_value: str | None) -> int:
    if secret["approval_mode"] == "approval_required" and not approve_high_risk:
        raise ValueError(
            f"{secret_id} is high-risk and requires the {secret['command_contract']} approval path"
        )

    command, env = build_playbook_command(
        secret_id,
        mode=mode,
        force=force,
        approve_high_risk=approve_high_risk,
        new_value=new_value,
    )
    rotation_event = build_rotation_event(secret_id, secret, status="started", mode=mode, command=command)
    result = run_command(command, capture_output=True)
    if result.returncode == 0:
        success_event = rotation_event | {"status": "succeeded"}
        try:
            maybe_emit_success(success_event)
        except urllib.error.URLError:
            pass
        if result.stdout:
            print(result.stdout.strip())
        return 0

    failure_event = rotation_event | {"status": "failed"}
    error_text = (result.stderr or result.stdout or "secret rotation playbook failed").strip()
    glitchtip_event = build_glitchtip_event(secret_id, secret, failure_event, error_text)
    try:
        maybe_emit_failure(failure_event, glitchtip_event)
    except urllib.error.URLError:
        pass
    if result.stdout:
        print(result.stdout.strip())
    raise RuntimeError(error_text)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect, validate, or execute the repo-managed secret rotation contract."
    )
    parser.add_argument("--validate", action="store_true", help="Validate the secret catalog.")
    parser.add_argument("--list", action="store_true", help="List managed secrets.")
    parser.add_argument("--secret", help="Show or execute one managed secret.")
    parser.add_argument("--plan", action="store_true", help="Run the secret-rotation playbook in plan mode.")
    parser.add_argument("--apply", action="store_true", help="Run the secret-rotation playbook in apply mode.")
    parser.add_argument("--force", action="store_true", help="Force execution even if the secret is not yet due.")
    parser.add_argument(
        "--approve-high-risk",
        action="store_true",
        help="Acknowledge that the high-risk command contract approval path has been satisfied.",
    )
    parser.add_argument("--new-value", help="Override the generated value with an explicit secret value.")
    parser.add_argument("--now", help="Evaluate due-state relative to an explicit ISO-8601 timestamp.")
    args = parser.parse_args()

    if sum(bool(flag) for flag in (args.validate, args.list, args.plan, args.apply, bool(args.secret))) == 0:
        parser.print_help()
        return 0

    try:
        secret_manifest = load_secret_manifest()
        validate_secret_manifest(secret_manifest)
        catalog = load_secret_catalog()
        validate_secret_catalog(catalog, secret_manifest)
        now = normalized_now(args.now)
    except (OSError, ValueError, RuntimeError) as exc:
        return emit_cli_error("Secret rotation", exc)

    if args.validate:
        print(f"Secret catalog OK: {SECRET_CATALOG_PATH}")
        return 0

    if args.list:
        return list_catalog(catalog, now=now)

    if not args.secret:
        parser.error("--secret is required for show, --plan, or --apply")

    secret = catalog["secrets"].get(args.secret)
    if secret is None:
        return emit_cli_error("Secret rotation", ValueError(f"Unknown secret id: {args.secret}"))

    if not args.plan and not args.apply:
        return show_secret(args.secret, secret, now=now)

    try:
        return run_rotation(
            args.secret,
            secret,
            mode="apply" if args.apply else "plan",
            force=args.force,
            approve_high_risk=args.approve_high_risk,
            new_value=args.new_value,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Secret rotation", exc)


if __name__ == "__main__":
    sys.exit(main())
