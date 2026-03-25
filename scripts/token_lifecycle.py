#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controller_automation_toolkit import load_yaml
from platform.ledger import LedgerWriter


UTC = dt.timezone.utc
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "token-policy.yaml"
DEFAULT_INVENTORY_PATH = REPO_ROOT / "config" / "token-inventory.yaml"
DEFAULT_AUDIT_RECEIPT_DIR = REPO_ROOT / "receipts" / "token-lifecycle"
DEFAULT_INCIDENT_DIR = REPO_ROOT / "receipts" / "security-incidents"
DEFAULT_LEDGER_FILE = REPO_ROOT / ".local" / "state" / "ledger" / "ledger.events.jsonl"
DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def utc_now() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> dt.datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min, tzinfo=UTC)
    if not isinstance(value, str):
        raise ValueError(f"unsupported timestamp value: {value!r}")
    normalized = value.strip()
    if not normalized:
        return None
    if DATE_ONLY_PATTERN.match(normalized):
        return dt.datetime.combine(dt.date.fromisoformat(normalized), dt.time.min, tzinfo=UTC)
    parsed = dt.datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_int(value: Any, path: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    return [require_str(item, f"{path}[{index}]") for index, item in enumerate(items)]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "token"


def render_template(value: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        resolved = context.get(key)
        return "" if resolved is None else str(resolved)

    return TEMPLATE_PATTERN.sub(replace, value)


def validate_policy_data(payload: Any) -> dict[str, dict[str, Any]]:
    payload = require_mapping(payload, "config/token-policy.yaml")
    require_str(payload.get("schema_version"), "config/token-policy.yaml.schema_version")
    classes = require_list(payload.get("token_classes"), "config/token-policy.yaml.token_classes")
    if not classes:
        raise ValueError("config/token-policy.yaml.token_classes must not be empty")
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(classes):
        path = f"config/token-policy.yaml.token_classes[{index}]"
        item = require_mapping(item, path)
        class_name = require_str(item.get("class"), f"{path}.class")
        if class_name in result:
            raise ValueError(f"duplicate token class '{class_name}' in config/token-policy.yaml")
        require_int(item.get("max_ttl_days"), f"{path}.max_ttl_days", 1)
        require_int(item.get("warning_window_days"), f"{path}.warning_window_days", 0)
        require_int(item.get("enforcement_grace_days"), f"{path}.enforcement_grace_days", 0)
        require_str(item.get("rotation_trigger"), f"{path}.rotation_trigger")
        require_str(item.get("storage"), f"{path}.storage")
        require_str(item.get("revocation_workflow"), f"{path}.revocation_workflow")
        require_str(item.get("on_exposure"), f"{path}.on_exposure")
        result[class_name] = item
    return result


def validate_inventory_data(payload: Any, policy: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    payload = require_mapping(payload, "config/token-inventory.yaml")
    require_str(payload.get("schema_version"), "config/token-inventory.yaml.schema_version")
    tokens = require_list(payload.get("tokens"), "config/token-inventory.yaml.tokens")
    if not tokens:
        raise ValueError("config/token-inventory.yaml.tokens must not be empty")
    seen_ids: set[str] = set()
    for index, token in enumerate(tokens):
        path = f"config/token-inventory.yaml.tokens[{index}]"
        token = require_mapping(token, path)
        token_id = require_str(token.get("id"), f"{path}.id")
        if token_id in seen_ids:
            raise ValueError(f"duplicate token id '{token_id}' in config/token-inventory.yaml")
        seen_ids.add(token_id)
        token_class = require_str(token.get("token_class"), f"{path}.token_class")
        if token_class not in policy:
            raise ValueError(f"{path}.token_class references unknown token class '{token_class}'")
        require_str(token.get("owner_service"), f"{path}.owner_service")
        require_str(token.get("subject"), f"{path}.subject")
        issued_at = parse_timestamp(token.get("issued_at"))
        if issued_at is None:
            raise ValueError(f"{path}.issued_at must be a timestamp")
        expires_at = parse_timestamp(token.get("expires_at"))
        if expires_at is not None and expires_at <= issued_at:
            raise ValueError(f"{path}.expires_at must be later than {path}.issued_at")
        require_str(token.get("storage_ref"), f"{path}.storage_ref")
        permissions = token.get("permissions", [])
        if permissions:
            require_string_list(permissions, f"{path}.permissions")
        workflows = token.get("workflows", {})
        if workflows:
            workflows = require_mapping(workflows, f"{path}.workflows")
            for key, value in workflows.items():
                require_str(key, f"{path}.workflows key '{key}'")
                require_str(value, f"{path}.workflows.{key}")
        hooks = token.get("hooks", {})
        if hooks:
            hooks = require_mapping(hooks, f"{path}.hooks")
            for key, value in hooks.items():
                hook_path = f"{path}.hooks.{key}"
                value = require_mapping(value, hook_path)
                if require_str(value.get("kind"), f"{hook_path}.kind") != "command":
                    raise ValueError(f"{hook_path}.kind must be 'command'")
                command = require_list(value.get("command"), f"{hook_path}.command")
                if not command:
                    raise ValueError(f"{hook_path}.command must not be empty")
                for command_index, part in enumerate(command):
                    require_str(part, f"{hook_path}.command[{command_index}]")
                env = value.get("env", {})
                if env:
                    env = require_mapping(env, f"{hook_path}.env")
                    for env_key, env_value in env.items():
                        require_str(env_key, f"{hook_path}.env key '{env_key}'")
                        require_str(env_value, f"{hook_path}.env.{env_key}")
    return tokens


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, dict[str, Any]]:
    return validate_policy_data(load_yaml(path))


def load_inventory(
    path: Path = DEFAULT_INVENTORY_PATH,
    *,
    policy: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    resolved_policy = load_policy() if policy is None else policy
    return validate_inventory_data(load_yaml(path), resolved_policy)


def build_context(token: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    context = {
        "token_id": token["id"],
        "token_class": token["token_class"],
        "owner_service": token["owner_service"],
        "subject": token["subject"],
        "storage_ref": token["storage_ref"],
    }
    if extra:
        context.update({key: value for key, value in extra.items() if value is not None})
    return context


def execute_hook(
    hook_name: str,
    hook: dict[str, Any] | None,
    *,
    token: dict[str, Any],
    context: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    if hook is None:
        return {"status": "missing", "hook": hook_name}

    if hook.get("kind") != "command":
        return {"status": "blocked", "hook": hook_name, "reason": "unsupported hook kind"}

    command = [render_template(part, context) for part in hook["command"]]
    payload: dict[str, Any] = {
        "status": "planned" if dry_run else "running",
        "hook": hook_name,
        "kind": "command",
        "command": command,
        "command_str": " ".join(shlex.quote(part) for part in command),
    }

    env = dict(os.environ)
    for key, value in require_mapping(hook.get("env", {}), f"hook {hook_name}.env").items():
        env[key] = render_template(str(value), context)
    cwd_value = hook.get("cwd")
    cwd = REPO_ROOT
    if cwd_value:
        cwd = Path(render_template(str(cwd_value), context))
        if not cwd.is_absolute():
            cwd = REPO_ROOT / cwd
    if dry_run:
        return payload

    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    payload.update(
        {
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    )
    if result.stdout.strip():
        try:
            payload["result"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return payload


def build_token_record(token: dict[str, Any], policy: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    issued_at = parse_timestamp(token["issued_at"])
    assert issued_at is not None
    expires_at = parse_timestamp(token.get("expires_at"))
    max_ttl_days = int(policy["max_ttl_days"])
    warning_window_days = int(policy["warning_window_days"])
    if expires_at is None:
        expires_at = issued_at + dt.timedelta(days=max_ttl_days)
    age_days = max((now - issued_at).days, 0)
    days_until_expiry = (expires_at - now).days
    overdue_days = max((now - expires_at).days, 0) if now > expires_at else 0
    if now >= expires_at:
        state = "expired"
    elif days_until_expiry <= warning_window_days:
        state = "warning"
    else:
        state = "healthy"

    action = "none"
    if state == "expired":
        action = "rotation_required"
    elif state == "warning":
        action = "rotation_due_soon"

    return {
        "token_id": token["id"],
        "token_class": token["token_class"],
        "owner_service": token["owner_service"],
        "subject": token["subject"],
        "issued_at": isoformat(issued_at),
        "expires_at": isoformat(expires_at),
        "age_days": age_days,
        "days_until_expiry": days_until_expiry,
        "warning_window_days": warning_window_days,
        "enforcement_grace_days": int(policy["enforcement_grace_days"]),
        "state": state,
        "overdue_days": overdue_days,
        "action": action,
        "permissions": list(token.get("permissions", [])),
        "workflows": dict(token.get("workflows", {})),
    }


def token_lookup(tokens: list[dict[str, Any]], token_id: str) -> dict[str, Any]:
    for token in tokens:
        if token["id"] == token_id:
            return token
    raise ValueError(f"unknown token id '{token_id}'")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def ledger_writer() -> LedgerWriter:
    return LedgerWriter(file_path=DEFAULT_LEDGER_FILE)


def maybe_write_audit_event(report: dict[str, Any]) -> None:
    writer = ledger_writer()
    writer.write(
        event_type="secret.audited",
        actor="token_lifecycle_audit",
        target_kind="secret",
        target_id="token_inventory",
        after_state=report["summary"],
        metadata={
            "receipt_path": report.get("receipt_path"),
            "findings_total": report["summary"]["findings_total"],
            "expired_total": report["summary"]["expired"],
        },
    )


def maybe_write_rotation_event(token: dict[str, Any], result: dict[str, Any]) -> None:
    writer = ledger_writer()
    writer.write(
        event_type="secret.rotated",
        actor="token_lifecycle",
        target_kind="secret",
        target_id=token["id"],
        after_state=result.get("result"),
        receipt=result,
        metadata={"token_class": token["token_class"], "owner_service": token["owner_service"]},
    )


def maybe_write_revocation_event(token: dict[str, Any], result: dict[str, Any]) -> None:
    writer = ledger_writer()
    writer.write(
        event_type="secret.revoked",
        actor="token_exposure_response",
        target_kind="secret",
        target_id=token["id"],
        after_state=result.get("result"),
        receipt=result,
        metadata={"token_class": token["token_class"], "owner_service": token["owner_service"]},
    )


def maybe_write_incident_event(token: dict[str, Any], report: dict[str, Any]) -> None:
    writer = ledger_writer()
    writer.write(
        event_type="incident.opened",
        actor="token_exposure_response",
        target_kind="secret",
        target_id=token["id"],
        after_state={"status": report["status"], "incident_path": report.get("incident_path")},
        metadata={
            "token_class": token["token_class"],
            "owner_service": token["owner_service"],
            "incident_id": report["incident_id"],
        },
    )


def rotate_token(
    token: dict[str, Any],
    *,
    dry_run: bool,
    reason: str,
) -> dict[str, Any]:
    context = build_context(token, {"rotation_reason": reason})
    hooks = dict(token.get("hooks", {}))
    rotate_hook = hooks.get("rotate")
    result = execute_hook("rotate", rotate_hook, token=token, context=context, dry_run=dry_run)
    if result["status"] == "missing":
        workflow = dict(token.get("workflows", {})).get("rotate")
        if workflow:
            return {"status": "planned" if dry_run else "blocked", "workflow": workflow, "reason": reason}
        return {"status": "blocked", "reason": "rotate hook is not configured"}
    if result["status"] == "ok" and not dry_run:
        maybe_write_rotation_event(token, result)
    return result


def revoke_token(
    token: dict[str, Any],
    *,
    dry_run: bool,
    reason: str,
) -> dict[str, Any]:
    context = build_context(token, {"revocation_reason": reason})
    hooks = dict(token.get("hooks", {}))
    revoke_hook = hooks.get("revoke")
    result = execute_hook("revoke", revoke_hook, token=token, context=context, dry_run=dry_run)
    if result["status"] == "missing":
        workflow = dict(token.get("workflows", {})).get("exposure_response")
        if workflow and dry_run:
            return {"status": "planned", "workflow": workflow, "reason": reason}
        return {"status": "blocked", "reason": "revoke hook is not configured"}
    if result["status"] == "ok" and not dry_run:
        maybe_write_revocation_event(token, result)
    return result


def run_audit(
    *,
    policy_path: Path = DEFAULT_POLICY_PATH,
    inventory_path: Path = DEFAULT_INVENTORY_PATH,
    receipt_dir: Path = DEFAULT_AUDIT_RECEIPT_DIR,
    now: dt.datetime | None = None,
    execute_remediations: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved_now = utc_now() if now is None else now
    policy = load_policy(policy_path)
    tokens = load_inventory(inventory_path, policy=policy)
    findings: list[dict[str, Any]] = []
    remediations: list[dict[str, Any]] = []
    summary = {"total": 0, "healthy": 0, "warning": 0, "expired": 0, "findings_total": 0}

    for token in tokens:
        token_policy = policy[token["token_class"]]
        finding = build_token_record(token, token_policy, resolved_now)
        findings.append(finding)
        summary["total"] += 1
        summary[finding["state"]] += 1
        if finding["state"] != "healthy":
            summary["findings_total"] += 1
            if (
                execute_remediations
                and finding["state"] == "expired"
                and finding["overdue_days"] > finding["enforcement_grace_days"]
            ):
                remediations.append(
                    {
                        "token_id": token["id"],
                        "result": rotate_token(
                            token,
                            dry_run=dry_run,
                            reason="ttl_overdue_inventory_audit",
                        ),
                    }
                )

    timestamp = resolved_now.strftime("%Y%m%dT%H%M%SZ")
    receipt_path = receipt_dir / f"{timestamp}-audit-token-inventory.json"
    report = {
        "status": "ok" if summary["findings_total"] == 0 else "attention_required",
        "run_at": isoformat(resolved_now),
        "summary": summary,
        "findings": findings,
        "remediations": remediations,
        "receipt_path": display_path(receipt_path),
    }
    write_json(receipt_path, report)
    maybe_write_audit_event(report)
    return report


def default_exposure_window(token: dict[str, Any]) -> dict[str, Any]:
    first_possible_use = token.get("last_used_at") or token["issued_at"]
    return {
        "status": "derived",
        "earliest_use": isoformat(parse_timestamp(first_possible_use) or parse_timestamp(token["issued_at"]) or utc_now()),
        "latest_known_use": token.get("last_used_at"),
    }


def default_impact_assessment(token: dict[str, Any], exposure_source: str, notes: str) -> dict[str, Any]:
    permissions = list(token.get("permissions", []))
    if permissions:
        scope = ", ".join(permissions)
        summary = f"Exposed token could reach: {scope}."
    else:
        summary = f"Exposed token scope is limited to owner service '{token['owner_service']}'."
    if exposure_source:
        summary = f"{summary} Exposure source: {exposure_source}."
    if notes:
        summary = f"{summary} Notes: {notes}."
    return {"status": "derived", "summary": summary, "permissions": permissions}


def run_exposure_response(
    *,
    token_id: str,
    policy_path: Path = DEFAULT_POLICY_PATH,
    inventory_path: Path = DEFAULT_INVENTORY_PATH,
    incident_dir: Path = DEFAULT_INCIDENT_DIR,
    now: dt.datetime | None = None,
    exposure_source: str = "",
    notes: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved_now = utc_now() if now is None else now
    policy = load_policy(policy_path)
    tokens = load_inventory(inventory_path, policy=policy)
    token = token_lookup(tokens, token_id)
    token_policy = policy[token["token_class"]]
    hooks = dict(token.get("hooks", {}))
    policy_mode = str(token_policy["on_exposure"])
    incident_id = f"token-exposure-{resolved_now.strftime('%Y%m%dT%H%M%SZ')}-{slugify(token_id)}"
    steps: list[dict[str, Any]] = []

    usage_result = execute_hook(
        "audit_usage",
        hooks.get("audit_usage"),
        token=token,
        context=build_context(token, {"exposure_source": exposure_source, "exposure_notes": notes}),
        dry_run=dry_run,
    )
    if usage_result["status"] == "missing":
        usage_result = default_exposure_window(token)
    steps.append({"id": "identify-exposure-window", "result": usage_result})

    revocation_required = policy_mode != "token_already_expired"
    if revocation_required:
        revocation_result = revoke_token(
            token,
            dry_run=dry_run,
            reason=f"token_exposure:{exposure_source or 'unspecified'}",
        )
    else:
        revocation_result = {"status": "skipped", "reason": "policy marks token class as already expired on exposure"}
    steps.append({"id": "immediate-revocation", "result": revocation_result})

    rotation_result = rotate_token(
        token,
        dry_run=dry_run,
        reason="post_exposure_replacement",
    )
    steps.append({"id": "replacement-issuance", "result": rotation_result})

    if "session_invalidation" in policy_mode:
        invalidate_result = execute_hook(
            "invalidate_sessions",
            hooks.get("invalidate_sessions"),
            token=token,
            context=build_context(token, {"exposure_source": exposure_source}),
            dry_run=dry_run,
        )
        if invalidate_result["status"] == "missing":
            invalidate_result = {"status": "blocked" if not dry_run else "planned", "reason": "session invalidation hook is not configured"}
    else:
        invalidate_result = {"status": "skipped", "reason": "token class does not require session invalidation"}
    steps.append({"id": "session-invalidation", "result": invalidate_result})

    impact_result = execute_hook(
        "assess_impact",
        hooks.get("assess_impact"),
        token=token,
        context=build_context(token, {"exposure_source": exposure_source, "exposure_notes": notes}),
        dry_run=dry_run,
    )
    if impact_result["status"] == "missing":
        impact_result = default_impact_assessment(token, exposure_source, notes)
    steps.append({"id": "impact-assessment", "result": impact_result})

    status = "completed"
    required_steps = [revocation_result, rotation_result]
    if any(step["status"] in {"error", "blocked"} for step in required_steps):
        status = "blocked"

    incident_payload = {
        "incident_id": incident_id,
        "status": status,
        "opened_at": isoformat(resolved_now),
        "token": {
            "id": token["id"],
            "token_class": token["token_class"],
            "owner_service": token["owner_service"],
            "subject": token["subject"],
        },
        "exposure_source": exposure_source or "unspecified",
        "notes": notes,
        "steps": steps,
    }
    incident_path = incident_dir / f"{incident_id}.json"
    write_json(incident_path, incident_payload)

    report = {
        "incident_id": incident_id,
        "status": status,
        "opened_at": isoformat(resolved_now),
        "incident_path": display_path(incident_path),
        "steps": steps,
    }
    maybe_write_incident_event(token, report)
    return report


def print_report(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit and respond to managed API token lifecycle events.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY_PATH))
    parser.add_argument("--now", help="Override the current UTC timestamp for deterministic runs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate the token policy and inventory.")
    validate.add_argument("--print-json", action="store_true")

    audit = subparsers.add_parser("audit", help="Audit the token inventory against the policy.")
    audit.add_argument("--receipt-dir", default=str(DEFAULT_AUDIT_RECEIPT_DIR))
    audit.add_argument("--execute-remediations", action="store_true")
    audit.add_argument("--dry-run", action="store_true")
    audit.add_argument("--print-report-json", action="store_true")

    rotate = subparsers.add_parser("rotate", help="Rotate one token through its configured hook contract.")
    rotate.add_argument("--token-id", required=True)
    rotate.add_argument("--dry-run", action="store_true")
    rotate.add_argument("--print-report-json", action="store_true")

    exposure = subparsers.add_parser("exposure-response", help="Execute the exposure response workflow for one token.")
    exposure.add_argument("--token-id", required=True)
    exposure.add_argument("--incident-dir", default=str(DEFAULT_INCIDENT_DIR))
    exposure.add_argument("--exposure-source", default="")
    exposure.add_argument("--notes", default="")
    exposure.add_argument("--dry-run", action="store_true")
    exposure.add_argument("--print-report-json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    now = parse_timestamp(args.now) if args.now else None
    policy_path = Path(args.policy)
    inventory_path = Path(args.inventory)

    try:
        if args.command == "validate":
            policy = load_policy(policy_path)
            inventory = load_inventory(inventory_path, policy=policy)
            payload = {
                "status": "ok",
                "token_classes": sorted(policy),
                "token_count": len(inventory),
            }
            print_report(payload, as_json=args.print_json)
            return 0

        if args.command == "audit":
            payload = run_audit(
                policy_path=policy_path,
                inventory_path=inventory_path,
                receipt_dir=Path(args.receipt_dir),
                now=now,
                execute_remediations=args.execute_remediations,
                dry_run=args.dry_run,
            )
            print_report(payload, as_json=args.print_report_json)
            return 0 if payload["summary"]["findings_total"] == 0 else 2

        policy = load_policy(policy_path)
        inventory = load_inventory(inventory_path, policy=policy)
        token = token_lookup(inventory, args.token_id)

        if args.command == "rotate":
            payload = rotate_token(token, dry_run=args.dry_run, reason="manual_rotation_request")
            print_report(payload, as_json=args.print_report_json)
            return 0 if payload["status"] in {"ok", "planned"} else 2

        if args.command == "exposure-response":
            payload = run_exposure_response(
                token_id=args.token_id,
                policy_path=policy_path,
                inventory_path=inventory_path,
                incident_dir=Path(args.incident_dir),
                now=now,
                exposure_source=args.exposure_source,
                notes=args.notes,
                dry_run=args.dry_run,
            )
            print_report(payload, as_json=args.print_report_json)
            return 0 if payload["status"] == "completed" else 2

        raise ValueError(f"unsupported command '{args.command}'")
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"token lifecycle error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
