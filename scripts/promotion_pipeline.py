#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from command_catalog import evaluate_approval, load_command_catalog, validate_command_catalog
from controller_automation_toolkit import (
    REPO_ROOT,
    emit_cli_error,
    load_json,
    load_yaml,
    run_command,
    write_json,
)
from live_apply_receipts import (
    RECEIPTS_DIR,
    load_receipt,
    receipt_relative_path,
    resolve_receipt_path,
    validate_receipt,
)
from mutation_audit import build_event, emit_event_best_effort, utc_now_iso
from workflow_catalog import (
    load_secret_manifest,
    load_workflow_catalog,
    validate_secret_manifest,
    validate_workflow_catalog,
)


PROMOTION_RECEIPTS_DIR = REPO_ROOT / "receipts" / "promotions"
STAGING_RECEIPTS_DIR = RECEIPTS_DIR / "staging"
VERSION_PATH = REPO_ROOT / "VERSION"
STACK_PATH = REPO_ROOT / "versions" / "stack.yaml"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
FINDINGS_PATH = REPO_ROOT / ".local" / "platform-observation" / "latest" / "findings.json"
ALLOWED_GATE_DECISIONS = {"approved", "rejected", "bypassed"}
ALLOWED_GATE_ACTOR_CLASSES = {"operator", "agent", "service", "automation"}


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


def require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def load_catalog_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    secret_manifest = load_secret_manifest()
    validate_secret_manifest(secret_manifest)
    workflow_catalog = load_workflow_catalog()
    validate_workflow_catalog(workflow_catalog, secret_manifest)
    command_catalog = load_command_catalog()
    validate_command_catalog(command_catalog, workflow_catalog, secret_manifest)
    return secret_manifest, workflow_catalog, command_catalog


def iso_to_datetime(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def current_repo_version() -> str:
    return VERSION_PATH.read_text().strip()


def current_platform_version() -> str:
    stack = load_yaml(STACK_PATH)
    return str(stack["platform_version"])


def git_output(*args: str) -> str:
    result = run_command(["git", *args], cwd=REPO_ROOT)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def current_branch() -> str:
    return git_output("rev-parse", "--abbrev-ref", "HEAD")


def current_commit() -> str:
    return git_output("rev-parse", "HEAD")


def load_service_index() -> dict[str, dict[str, Any]]:
    catalog = load_json(SERVICE_CATALOG_PATH)
    services = require_list(catalog.get("services"), "service-capability-catalog.services")
    indexed: dict[str, dict[str, Any]] = {}
    for index, service in enumerate(services):
        service = require_mapping(service, f"service-capability-catalog.services[{index}]")
        service_id = require_str(service.get("id"), f"service-capability-catalog.services[{index}].id")
        indexed[service_id] = service
    return indexed


def service_aliases(service_id: str, service: dict[str, Any]) -> set[str]:
    aliases = {
        service_id.lower(),
        require_str(service.get("name"), f"service '{service_id}'.name").lower(),
        require_str(service.get("vm"), f"service '{service_id}'.vm").lower(),
    }
    for key in ("public_url", "internal_url", "subdomain"):
        value = service.get(key)
        if isinstance(value, str) and value.strip():
            aliases.add(value.lower())
    return aliases


def extract_address(service: dict[str, Any]) -> str | None:
    for key in ("internal_url", "public_url"):
        value = service.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        parsed = urlparse(value)
        if parsed.hostname:
            return parsed.hostname
    return None


def load_findings(path: Path = FINDINGS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    findings = require_list(payload, str(path))
    return [require_mapping(item, f"{path}[{index}]") for index, item in enumerate(findings)]


def finding_mentions_service(finding: dict[str, Any], aliases: set[str]) -> bool:
    flattened = json.dumps(finding, sort_keys=True).lower()
    return any(alias in flattened for alias in aliases)


def build_stage_health_summary(stage_receipt: dict[str, Any]) -> dict[str, Any]:
    checks = []
    all_passed = True
    for item in stage_receipt["verification"]:
        passed = item["result"] == "pass"
        all_passed = all_passed and passed
        checks.append(
            {
                "check": item["check"],
                "result": item["result"],
                "passed": passed,
                "observed": item["observed"],
            }
        )
    return {"passed": all_passed, "checks": checks}


def recorded_at_for_receipt(receipt: dict[str, Any]) -> dt.datetime:
    if isinstance(receipt.get("recorded_at"), str) and receipt["recorded_at"].strip():
        return iso_to_datetime(receipt["recorded_at"])
    return dt.datetime.fromisoformat(f"{receipt['recorded_on']}T00:00:00+00:00")


def check_promotion_gate(
    *,
    service_id: str,
    staging_receipt_ref: str,
    requester_class: str,
    approver_classes: list[str],
    findings_path: Path = FINDINGS_PATH,
) -> dict[str, Any]:
    _secret_manifest, workflow_catalog, command_catalog = load_catalog_context()
    service_index = load_service_index()
    if service_id not in service_index:
        raise ValueError(f"unknown service '{service_id}'")

    staging_receipt_path = resolve_receipt_path(staging_receipt_ref)
    if not staging_receipt_path.is_file():
        raise ValueError(f"staging receipt not found: {staging_receipt_ref}")
    if not staging_receipt_path.is_relative_to(STAGING_RECEIPTS_DIR):
        raise ValueError("staging receipt must be stored under receipts/live-applies/staging/")

    stage_receipt = load_receipt(staging_receipt_path)
    validate_receipt(stage_receipt, staging_receipt_path, workflow_catalog)
    if stage_receipt.get("environment") != "staging":
        raise ValueError("staging receipt must declare environment 'staging'")

    recorded_at = recorded_at_for_receipt(stage_receipt)
    age = dt.datetime.now(dt.timezone.utc) - recorded_at
    stage_health = build_stage_health_summary(stage_receipt)

    approval = evaluate_approval(
        command_catalog,
        workflow_catalog,
        "promote-to-production",
        requester_class,
        approver_classes,
        preflight_passed=True,
        validation_passed=True,
        receipt_planned=True,
        self_approve=False,
        break_glass=False,
    )

    reasons = list(approval["reasons"])
    if age > dt.timedelta(hours=24):
        reasons.append("staging receipt is older than 24 hours")
    if not stage_health["passed"]:
        reasons.append("staging receipt verification is not clean")

    service = service_index[service_id]
    aliases = service_aliases(service_id, service)
    blocking_findings = [
        finding
        for finding in load_findings(findings_path)
        if finding.get("severity") == "critical" and finding_mentions_service(finding, aliases)
    ]
    if blocking_findings:
        reasons.append(f"open critical findings exist for service '{service_id}'")

    return {
        "service": service_id,
        "playbook": service_id,
        "staging_receipt": str(receipt_relative_path(staging_receipt_path)),
        "staging_health_check": stage_health,
        "approval": approval,
        "blocking_findings": blocking_findings,
        "gate_decision": "approved" if not reasons else "rejected",
        "reasons": reasons,
    }


def build_live_apply_receipt(
    *,
    receipt_id: str,
    workflow_id: str,
    adr: str,
    summary: str,
    targets: list[dict[str, Any]],
    verification: list[dict[str, str]],
    evidence_refs: list[str],
    notes: list[str],
    environment: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "receipt_id": receipt_id,
        "environment": environment,
        "applied_on": today_utc(),
        "recorded_on": today_utc(),
        "recorded_at": utc_now_iso(),
        "recorded_by": "codex",
        "source_commit": current_commit(),
        "repo_version_context": current_repo_version(),
        "workflow_id": workflow_id,
        "adr": adr,
        "summary": summary,
        "targets": targets,
        "verification": verification,
        "evidence_refs": evidence_refs,
        "notes": notes,
    }
    return payload


def build_service_targets(service_id: str, service: dict[str, Any]) -> list[dict[str, Any]]:
    target = {
        "kind": "host" if service["vm"] == "proxmox_florin" else "guest",
        "name": service["vm"],
    }
    address = extract_address(service)
    if address:
        target["address"] = address
    if isinstance(service.get("vmid"), int):
        target["vmid"] = service["vmid"]
    return [target]


def build_promotion_receipt(
    *,
    promotion_id: str,
    branch: str,
    service_id: str,
    playbook: str,
    staging_receipt: str,
    stage_health: dict[str, Any],
    gate_decision: str,
    gate_actor_class: str,
    gate_actor_id: str,
    prod_receipt: str | None,
    notes: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "promotion_id": promotion_id,
        "branch": branch,
        "service": service_id,
        "playbook": playbook,
        "staging_receipt": staging_receipt,
        "staging_health_check": stage_health,
        "gate_decision": gate_decision,
        "gate_actor": {"class": gate_actor_class, "id": gate_actor_id},
        "prod_receipt": prod_receipt,
        "repo_version_context": current_repo_version(),
        "platform_version_context": current_platform_version(),
        "ts": utc_now_iso(),
        "notes": notes,
    }


def validate_promotion_receipt(receipt: dict[str, Any], path: Path) -> None:
    required_string_fields = (
        "schema_version",
        "promotion_id",
        "branch",
        "service",
        "playbook",
        "staging_receipt",
        "gate_decision",
        "repo_version_context",
        "platform_version_context",
        "ts",
    )
    for field in required_string_fields:
        require_str(receipt.get(field), f"{path.name}.{field}")

    if receipt["schema_version"] != "1.0.0":
        raise ValueError(f"{path.name}: unsupported schema_version '{receipt['schema_version']}'")
    if path.stem != receipt["promotion_id"]:
        raise ValueError(f"{path.name}: filename must match promotion_id '{receipt['promotion_id']}'")
    if receipt["gate_decision"] not in ALLOWED_GATE_DECISIONS:
        raise ValueError(f"{path.name}: gate_decision must be one of {sorted(ALLOWED_GATE_DECISIONS)}")
    iso_to_datetime(receipt["ts"])

    gate_actor = require_mapping(receipt.get("gate_actor"), f"{path.name}.gate_actor")
    actor_class = require_str(gate_actor.get("class"), f"{path.name}.gate_actor.class")
    if actor_class not in ALLOWED_GATE_ACTOR_CLASSES:
        raise ValueError(f"{path.name}: gate_actor.class must be one of {sorted(ALLOWED_GATE_ACTOR_CLASSES)}")
    require_str(gate_actor.get("id"), f"{path.name}.gate_actor.id")

    stage_health = require_mapping(receipt.get("staging_health_check"), f"{path.name}.staging_health_check")
    require_bool(stage_health.get("passed"), f"{path.name}.staging_health_check.passed")
    checks = require_list(stage_health.get("checks"), f"{path.name}.staging_health_check.checks")
    for index, item in enumerate(checks):
        item = require_mapping(item, f"{path.name}.staging_health_check.checks[{index}]")
        require_str(item.get("check"), f"{path.name}.staging_health_check.checks[{index}].check")
        require_str(item.get("result"), f"{path.name}.staging_health_check.checks[{index}].result")
        require_bool(item.get("passed"), f"{path.name}.staging_health_check.checks[{index}].passed")
        require_str(item.get("observed"), f"{path.name}.staging_health_check.checks[{index}].observed")

    staging_receipt_path = resolve_receipt_path(receipt["staging_receipt"])
    if not staging_receipt_path.exists():
        raise ValueError(f"{path.name}: staging receipt '{receipt['staging_receipt']}' does not exist")

    prod_receipt = receipt.get("prod_receipt")
    if prod_receipt is not None:
        prod_receipt = require_str(prod_receipt, f"{path.name}.prod_receipt")
        prod_receipt_path = resolve_receipt_path(prod_receipt)
        if not prod_receipt_path.exists():
            raise ValueError(f"{path.name}: prod receipt '{prod_receipt}' does not exist")
    elif receipt["gate_decision"] == "approved":
        raise ValueError(f"{path.name}: approved promotions must reference a prod_receipt")

    notes = receipt.get("notes", [])
    notes = require_list(notes, f"{path.name}.notes")
    for index, note in enumerate(notes):
        require_str(note, f"{path.name}.notes[{index}]")


def validate_promotion_receipts() -> int:
    receipt_paths = sorted(PROMOTION_RECEIPTS_DIR.glob("*.json"))
    seen_ids: set[str] = set()
    for path in receipt_paths:
        receipt = load_json(path)
        validate_promotion_receipt(receipt, path)
        if receipt["promotion_id"] in seen_ids:
            raise ValueError(f"duplicate promotion_id '{receipt['promotion_id']}'")
        seen_ids.add(receipt["promotion_id"])

    print(f"Promotion receipts OK: {PROMOTION_RECEIPTS_DIR} ({len(receipt_paths)} file(s))")
    return 0


def run_make(target: str, *vars_: str) -> dict[str, Any]:
    command = ["make", target, *vars_]
    result = run_command(command, cwd=REPO_ROOT)
    return {
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def emit_promotion_audit(
    *,
    action: str,
    target: str,
    outcome: str,
    correlation_id: str,
    evidence_ref: str,
) -> None:
    event = build_event(
        actor_class="automation",
        actor_id="promotion-pipeline",
        surface="manual",
        action=action,
        target=target,
        outcome=outcome,
        correlation_id=correlation_id,
        evidence_ref=evidence_ref,
    )
    emit_event_best_effort(event, context=f"promotion pipeline '{action}'", stderr=sys.stderr)


def promote_service(
    *,
    service_id: str,
    staging_receipt_ref: str,
    branch: str | None,
    requester_class: str,
    approver_classes: list[str],
    extra_args: str,
    dry_run: bool,
) -> dict[str, Any]:
    branch_name = branch or current_branch()
    if not branch_name.startswith(("codex/", "operator/")):
        raise ValueError("promotion requires a codex/ or operator/ branch, not main")

    validate_result = run_make("validate")
    if validate_result["returncode"] != 0:
        raise ValueError(f"make validate failed:\n{validate_result['stderr'] or validate_result['stdout']}")

    gate = check_promotion_gate(
        service_id=service_id,
        staging_receipt_ref=staging_receipt_ref,
        requester_class=requester_class,
        approver_classes=approver_classes,
    )
    if gate["gate_decision"] != "approved":
        raise ValueError("promotion gate rejected: " + "; ".join(gate["reasons"]))

    promotion_id = f"{today_utc()}-{service_id}-promotion-{uuid.uuid4().hex[:8]}"
    correlation_id = f"promotion:{promotion_id}"

    if dry_run:
        return {
            "status": "dry-run",
            "promotion_id": promotion_id,
            "branch": branch_name,
            "service": service_id,
            "validate": validate_result,
            "gate": gate,
        }

    prod_apply = run_make(
        "live-apply-service",
        f"service={service_id}",
        "env=production",
        f"EXTRA_ARGS={extra_args}".rstrip(),
    )
    if prod_apply["returncode"] != 0:
        emit_promotion_audit(
            action="promotion.execute",
            target=service_id,
            outcome="failure",
            correlation_id=correlation_id,
            evidence_ref=gate["staging_receipt"],
        )
        raise ValueError(f"production live apply failed:\n{prod_apply['stderr'] or prod_apply['stdout']}")

    service = load_service_index()[service_id]
    prod_receipt_id = f"{today_utc()}-{service_id}-production-promotion-{promotion_id.rsplit('-', 1)[-1]}"
    prod_receipt = build_live_apply_receipt(
        receipt_id=prod_receipt_id,
        workflow_id="deploy-and-promote",
        adr="0073",
        summary=(
            f"Promoted `{service_id}` from the staging receipt `{gate['staging_receipt']}` after a clean "
            f"validation pass, command-catalog approval, and successful production live apply."
        ),
        targets=build_service_targets(service_id, service),
        verification=[
            {
                "check": "Repository validation",
                "result": "pass",
                "observed": "The promotion pipeline ran `make validate` successfully before opening the production gate.",
            },
            {
                "check": "Staging gate",
                "result": "pass",
                "observed": f"The staged receipt `{gate['staging_receipt']}` was recent, clean, and had no blocking critical findings.",
            },
            {
                "check": "Production apply",
                "result": "pass",
                "observed": f"The production promotion command succeeded: `{prod_apply['command']}`.",
            },
        ],
        evidence_refs=[
            "docs/adr/0073-environment-promotion-gate-and-deployment-pipeline.md",
            "docs/runbooks/environment-promotion-pipeline.md",
            "config/command-catalog.json",
            "config/workflow-catalog.json",
            gate["staging_receipt"],
        ],
        notes=[
            f"Promotion branch: {branch_name}.",
            f"Approval classes: {', '.join(approver_classes)}.",
        ],
        environment="production",
    )
    prod_receipt_path = RECEIPTS_DIR / f"{prod_receipt_id}.json"
    write_json(prod_receipt_path, prod_receipt, indent=2)

    promotion_receipt = build_promotion_receipt(
        promotion_id=promotion_id,
        branch=branch_name,
        service_id=service_id,
        playbook=service_id,
        staging_receipt=gate["staging_receipt"],
        stage_health=gate["staging_health_check"],
        gate_decision="approved",
        gate_actor_class="operator",
        gate_actor_id=approver_classes[0] if approver_classes else requester_class,
        prod_receipt=str(receipt_relative_path(prod_receipt_path)),
        notes=[
            "This promotion record was generated by the repo-managed ADR 0073 promotion pipeline.",
            f"Production apply command: {prod_apply['command']}.",
        ],
    )
    promotion_receipt_path = PROMOTION_RECEIPTS_DIR / f"{promotion_id}.json"
    write_json(promotion_receipt_path, promotion_receipt, indent=2)

    emit_promotion_audit(
        action="promotion.execute",
        target=service_id,
        outcome="success",
        correlation_id=correlation_id,
        evidence_ref=str(receipt_relative_path(promotion_receipt_path)),
    )
    return {
        "status": "ok",
        "promotion_id": promotion_id,
        "branch": branch_name,
        "service": service_id,
        "validate": validate_result,
        "gate": gate,
        "production_apply": prod_apply,
        "prod_receipt": str(receipt_relative_path(prod_receipt_path)),
        "promotion_receipt": str(receipt_relative_path(promotion_receipt_path)),
    }


def emit_bypass_event(target: str, actor_id: str | None, correlation_id: str | None) -> dict[str, Any]:
    event = build_event(
        actor_class="operator",
        actor_id=actor_id or "break-glass-operator",
        surface="manual",
        action="promotion_bypassed",
        target=target,
        outcome="success",
        correlation_id=correlation_id,
        evidence_ref="docs/adr/0073-environment-promotion-gate-and-deployment-pipeline.md",
    )
    emit_event_best_effort(event, context="promotion bypass", stderr=sys.stderr)
    return event


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and execute the ADR 0073 promotion pipeline.")
    parser.add_argument("--validate", action="store_true", help="Validate all promotion receipts.")
    parser.add_argument("--check-gate", action="store_true", help="Evaluate the promotion gate for a staged receipt.")
    parser.add_argument("--promote", action="store_true", help="Run repository validation, evaluate the gate, and promote a service to production.")
    parser.add_argument("--emit-bypass-event", action="store_true", help="Emit the break-glass promotion bypass audit event.")
    parser.add_argument("--service", help="Service id from config/service-capability-catalog.json.")
    parser.add_argument("--staging-receipt", help="Path to a staging live-apply receipt.")
    parser.add_argument("--branch", help="Source branch for the promotion request.")
    parser.add_argument("--requester-class", default="human_operator", help="Requester identity class for the command gate.")
    parser.add_argument(
        "--approver-classes",
        default="human_operator",
        help="Comma-separated approver identity classes for the command gate.",
    )
    parser.add_argument("--extra-args", default="", help="Additional EXTRA_ARGS passed to the production live apply.")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate the promotion without mutating production.")
    parser.add_argument("--actor-id", help="Actor id for the break-glass bypass event.")
    parser.add_argument("--correlation-id", help="Explicit correlation id for the break-glass bypass event.")
    args = parser.parse_args()

    try:
        if args.validate:
            return validate_promotion_receipts()

        if args.emit_bypass_event:
            if not args.service:
                raise ValueError("--emit-bypass-event requires --service")
            print(json.dumps(emit_bypass_event(args.service, args.actor_id, args.correlation_id), indent=2))
            return 0

        approver_classes = [item.strip() for item in args.approver_classes.split(",") if item.strip()]
        if args.check_gate:
            if not args.service or not args.staging_receipt:
                raise ValueError("--check-gate requires --service and --staging-receipt")
            payload = check_promotion_gate(
                service_id=args.service,
                staging_receipt_ref=args.staging_receipt,
                requester_class=args.requester_class,
                approver_classes=approver_classes,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if payload["gate_decision"] == "approved" else 1

        if args.promote:
            if not args.service or not args.staging_receipt:
                raise ValueError("--promote requires --service and --staging-receipt")
            payload = promote_service(
                service_id=args.service,
                staging_receipt_ref=args.staging_receipt,
                branch=args.branch,
                requester_class=args.requester_class,
                approver_classes=approver_classes,
                extra_args=args.extra_args,
                dry_run=args.dry_run,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        parser.print_help()
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("Promotion pipeline", exc)


if __name__ == "__main__":
    sys.exit(main())
