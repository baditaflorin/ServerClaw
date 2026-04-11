#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Final

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from validation_toolkit import require_bool, require_int, require_list, require_mapping, require_str

from controller_automation_toolkit import emit_cli_error, load_json, repo_path
from correction_loops import (
    CORRECTION_LOOP_CATALOG_PATH,
    load_correction_loop_catalog,
    resolve_workflow_correction_loop,
    validate_correction_loop_catalog,
)
from mutation_audit import build_event, emit_event_best_effort
from workflow_catalog import (
    ALLOWED_LIVE_IMPACTS,
    load_secret_manifest,
    load_workflow_catalog,
    validate_secret_manifest,
    validate_workflow_catalog,
)
from platform.policy.engine import evaluate_command_approval_policy


COMMAND_CATALOG_PATH = repo_path("config", "command-catalog.json")
SUPPORTED_SCHEMA_VERSION: Final[str] = "1.0.0"
ALLOWED_IDENTITY_CLASSES = {"human_operator", "service_identity", "agent", "break_glass"}
ALLOWED_SCOPES = {"proxmox_host", "guest_runtime", "host_and_guest", "external_service"}
ALLOWED_EXECUTION_TRANSPORTS = {"ssh_systemd_run_make"}
ALLOWED_KILL_MODES = {"control-group", "mixed", "process", "none"}
MUTATION_AUDIT_ACTOR_CLASS_MAP = {
    "human_operator": "operator",
    "service_identity": "service",
    "agent": "agent",
    "break_glass": "operator",
}


def load_command_catalog() -> dict:
    return load_json(COMMAND_CATALOG_PATH)


def validate_string_mapping(value: object, path: str) -> dict[str, str]:
    mapping = require_mapping(value, path)
    result: dict[str, str] = {}
    for key, item in mapping.items():
        normalized_key = require_str(key, f"{path} key")
        result[normalized_key] = require_str(item, f"{path}.{normalized_key}")
    return result


def validate_identity_class_list(value: object, path: str) -> list[str]:
    items = require_list(value, path)
    if not items:
        raise ValueError(f"{path} must not be empty")
    result = []
    for index, item in enumerate(items):
        item = require_str(item, f"{path}[{index}]")
        if item not in ALLOWED_IDENTITY_CLASSES:
            raise ValueError(f"{path}[{index}] must be one of {sorted(ALLOWED_IDENTITY_CLASSES)}")
        result.append(item)
    return result


def validate_command_catalog(command_catalog: dict, workflow_catalog: dict, secret_manifest: dict) -> None:
    if command_catalog.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"command catalog must declare schema_version '{SUPPORTED_SCHEMA_VERSION}'")

    workflows = workflow_catalog["workflows"]
    secret_ids = set(secret_manifest["secrets"].keys())
    execution_profiles = require_mapping(command_catalog.get("execution_profiles"), "execution_profiles")
    if not execution_profiles:
        raise ValueError("execution_profiles must not be empty")
    for profile_id, profile in execution_profiles.items():
        profile = require_mapping(profile, f"execution_profiles.{profile_id}")
        require_str(profile_id, f"execution profile id '{profile_id}'")
        transport = require_str(profile.get("transport"), f"execution_profiles.{profile_id}.transport")
        if transport not in ALLOWED_EXECUTION_TRANSPORTS:
            raise ValueError(
                f"execution_profiles.{profile_id}.transport must be one of {sorted(ALLOWED_EXECUTION_TRANSPORTS)}"
            )
        require_str(profile.get("runtime_host"), f"execution_profiles.{profile_id}.runtime_host")
        require_str(profile.get("runtime_repo_root"), f"execution_profiles.{profile_id}.runtime_repo_root")
        require_str(
            profile.get("runtime_compat_repo_root"),
            f"execution_profiles.{profile_id}.runtime_compat_repo_root",
        )
        require_str(profile.get("effective_user"), f"execution_profiles.{profile_id}.effective_user")
        require_str(profile.get("working_directory"), f"execution_profiles.{profile_id}.working_directory")
        kill_mode = require_str(profile.get("kill_mode"), f"execution_profiles.{profile_id}.kill_mode")
        if kill_mode not in ALLOWED_KILL_MODES:
            raise ValueError(f"execution_profiles.{profile_id}.kill_mode must be one of {sorted(ALLOWED_KILL_MODES)}")
        require_str(profile.get("log_directory"), f"execution_profiles.{profile_id}.log_directory")
        require_str(profile.get("receipt_directory"), f"execution_profiles.{profile_id}.receipt_directory")
        if profile.get("env") is not None:
            validate_string_mapping(profile.get("env"), f"execution_profiles.{profile_id}.env")

    policies = require_mapping(command_catalog.get("approval_policies"), "approval_policies")
    if not policies:
        raise ValueError("approval_policies must not be empty")
    for policy_id, policy in policies.items():
        policy = require_mapping(policy, f"approval_policies.{policy_id}")
        require_str(policy_id, f"approval policy id '{policy_id}'")
        require_str(policy.get("description"), f"approval_policies.{policy_id}.description")
        validate_identity_class_list(
            policy.get("allowed_requester_classes"),
            f"approval_policies.{policy_id}.allowed_requester_classes",
        )
        validate_identity_class_list(
            policy.get("allowed_approver_classes"),
            f"approval_policies.{policy_id}.allowed_approver_classes",
        )
        require_int(policy.get("minimum_approvals"), f"approval_policies.{policy_id}.minimum_approvals", minimum=1)
        require_bool(policy.get("require_preflight"), f"approval_policies.{policy_id}.require_preflight")
        require_bool(policy.get("require_validation"), f"approval_policies.{policy_id}.require_validation")
        require_bool(policy.get("require_receipt_plan"), f"approval_policies.{policy_id}.require_receipt_plan")
        require_bool(policy.get("allow_self_approval"), f"approval_policies.{policy_id}.allow_self_approval")
        require_bool(policy.get("allow_break_glass"), f"approval_policies.{policy_id}.allow_break_glass")

    commands = require_mapping(command_catalog.get("commands"), "commands")
    if not commands:
        raise ValueError("commands must not be empty")

    covered_workflow_ids = set()
    for command_id, contract in commands.items():
        contract = require_mapping(contract, f"commands.{command_id}")
        require_str(command_id, f"command id '{command_id}'")
        require_str(contract.get("description"), f"commands.{command_id}.description")
        workflow_id = require_str(contract.get("workflow_id"), f"commands.{command_id}.workflow_id")
        if workflow_id not in workflows:
            raise ValueError(f"commands.{command_id}.workflow_id references unknown workflow '{workflow_id}'")
        workflow = workflows[workflow_id]
        covered_workflow_ids.add(workflow_id)
        live_impact = workflow["live_impact"]
        if live_impact not in ALLOWED_LIVE_IMPACTS or live_impact == "repo_only":
            raise ValueError(f"commands.{command_id}.workflow_id must reference a mutating non-repo-only workflow")

        scope = require_str(contract.get("scope"), f"commands.{command_id}.scope")
        if scope not in ALLOWED_SCOPES:
            raise ValueError(f"commands.{command_id}.scope must be one of {sorted(ALLOWED_SCOPES)}")

        approval_policy = require_str(contract.get("approval_policy"), f"commands.{command_id}.approval_policy")
        if approval_policy not in policies:
            raise ValueError(f"commands.{command_id}.approval_policy references unknown policy '{approval_policy}'")

        inputs = require_list(contract.get("inputs"), f"commands.{command_id}.inputs")
        if not inputs:
            raise ValueError(f"commands.{command_id}.inputs must not be empty")
        for index, item in enumerate(inputs):
            item = require_mapping(item, f"commands.{command_id}.inputs[{index}]")
            require_str(item.get("name"), f"commands.{command_id}.inputs[{index}].name")
            kind = require_str(item.get("kind"), f"commands.{command_id}.inputs[{index}].kind")
            require_bool(item.get("required"), f"commands.{command_id}.inputs[{index}].required")
            require_str(item.get("source"), f"commands.{command_id}.inputs[{index}].source")
            require_str(item.get("description"), f"commands.{command_id}.inputs[{index}].description")
            if kind == "controller_secret" and item["name"] not in secret_ids:
                raise ValueError(
                    f"commands.{command_id}.inputs[{index}].name references unknown secret '{item['name']}'"
                )

        preconditions = require_list(
            contract.get("expected_preconditions"),
            f"commands.{command_id}.expected_preconditions",
        )
        if not preconditions:
            raise ValueError(f"commands.{command_id}.expected_preconditions must not be empty")
        for index, item in enumerate(preconditions):
            require_str(item, f"commands.{command_id}.expected_preconditions[{index}]")

        evidence = require_mapping(contract.get("evidence"), f"commands.{command_id}.evidence")
        if not require_bool(
            evidence.get("live_apply_receipt_required"),
            f"commands.{command_id}.evidence.live_apply_receipt_required",
        ):
            raise ValueError(
                f"commands.{command_id}.evidence.live_apply_receipt_required must stay true for live mutation"
            )
        require_str(evidence.get("notes"), f"commands.{command_id}.evidence.notes")

        failure_guidance = require_mapping(contract.get("failure_guidance"), f"commands.{command_id}.failure_guidance")
        for field in ("stop_conditions", "rollback_guidance"):
            items = require_list(failure_guidance.get(field), f"commands.{command_id}.failure_guidance.{field}")
            if not items:
                raise ValueError(f"commands.{command_id}.failure_guidance.{field} must not be empty")
            for index, item in enumerate(items):
                require_str(item, f"commands.{command_id}.failure_guidance.{field}[{index}]")

        execution = require_mapping(contract.get("execution"), f"commands.{command_id}.execution")
        profile_id = require_str(execution.get("profile"), f"commands.{command_id}.execution.profile")
        if profile_id not in execution_profiles:
            raise ValueError(
                f"commands.{command_id}.execution.profile references unknown execution profile '{profile_id}'"
            )
        require_int(execution.get("timeout_seconds"), f"commands.{command_id}.execution.timeout_seconds", minimum=1)
        if workflows[workflow_id]["preferred_entrypoint"]["kind"] != "make_target":
            raise ValueError(
                f"commands.{command_id}.workflow_id must use a make_target preferred entrypoint for this execution model"
            )

    missing_contracts = sorted(
        workflow_id
        for workflow_id, workflow in workflows.items()
        if workflow["live_impact"] != "repo_only" and workflow_id not in covered_workflow_ids
    )
    if missing_contracts:
        raise ValueError("command catalog is missing contracts for mutating workflows: " + ", ".join(missing_contracts))


def list_commands(command_catalog: dict, workflow_catalog: dict) -> int:
    print(f"Command catalog: {COMMAND_CATALOG_PATH}")
    print("Available command contracts:")
    for command_id, contract in sorted(command_catalog["commands"].items()):
        workflow = workflow_catalog["workflows"][contract["workflow_id"]]
        print(
            f"  - {command_id} [{contract['approval_policy']}, {workflow['live_impact']}, "
            f"{workflow['lifecycle_status']}]: {workflow['preferred_entrypoint']['command']}"
        )
    return 0


def show_command(command_catalog: dict, workflow_catalog: dict, command_id: str) -> int:
    contract = command_catalog["commands"].get(command_id)
    if contract is None:
        print(f"Unknown command contract: {command_id}", file=sys.stderr)
        return 2

    workflow = workflow_catalog["workflows"][contract["workflow_id"]]
    policy = command_catalog["approval_policies"][contract["approval_policy"]]

    print(f"Command: {command_id}")
    print(f"Description: {contract['description']}")
    print(f"Workflow: {contract['workflow_id']}")
    print(f"Scope: {contract['scope']}")
    print(f"Live impact: {workflow['live_impact']}")
    print(f"Workflow lifecycle: {workflow['lifecycle_status']}")
    print(f"Entrypoint: {workflow['preferred_entrypoint']['command']}")
    print(f"Runbook: {workflow['owner_runbook']}")
    print(f"Approval policy: {contract['approval_policy']}")
    print(f"Policy summary: {policy['description']}")
    print("Inputs:")
    for item in contract["inputs"]:
        optionality = "required" if item["required"] else "optional"
        print(f"  - {item['name']} [{item['kind']}, {optionality}] from {item['source']}")
        print(f"    {item['description']}")
    print("Expected preconditions:")
    for item in contract["expected_preconditions"]:
        print(f"  - {item}")
    print("Verification commands:")
    for item in workflow["verification_commands"]:
        print(f"  - {item}")
    print("Evidence:")
    print(f"  - live_apply_receipt_required: {contract['evidence']['live_apply_receipt_required']}")
    print(f"  - {contract['evidence']['notes']}")
    print("Failure guidance:")
    for item in contract["failure_guidance"]["stop_conditions"]:
        print(f"  - stop: {item}")
    for item in contract["failure_guidance"]["rollback_guidance"]:
        print(f"  - rollback: {item}")
    execution = contract["execution"]
    profile = command_catalog["execution_profiles"][execution["profile"]]
    print("Execution:")
    print(f"  - profile: {execution['profile']}")
    print(f"  - runtime_host: {profile['runtime_host']}")
    print(f"  - effective_user: {profile['effective_user']}")
    print(f"  - working_directory: {profile['working_directory']}")
    print(f"  - timeout_seconds: {execution['timeout_seconds']}")
    print(f"  - kill_mode: {profile['kill_mode']}")
    print(f"  - log_directory: {profile['log_directory']}")
    print(f"  - receipt_directory: {profile['receipt_directory']}")
    if profile.get("env"):
        print(f"  - env: {json.dumps(profile['env'], sort_keys=True)}")
    if CORRECTION_LOOP_CATALOG_PATH.exists():
        correction_catalog = load_correction_loop_catalog()
        correction_loop = resolve_workflow_correction_loop(correction_catalog, contract["workflow_id"])
        if correction_loop is not None:
            print("Correction loop:")
            print(f"  - id: {correction_loop['id']}")
            print(f"  - invariant: {correction_loop['invariant']}")
            print(f"  - verification: {correction_loop['verification']['source']}")
            print(f"  - escalation: {correction_loop['escalation']['boundary']}")
    return 0


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def emit_approval_audit_event(
    *,
    command_id: str,
    requester_class: str,
    outcome: str,
    correlation_id: str | None,
    actor_id: str | None,
) -> None:
    event = build_event(
        actor_class=MUTATION_AUDIT_ACTOR_CLASS_MAP.get(requester_class, "operator"),
        actor_id=actor_id or os.environ.get("USER") or "unknown",
        surface="command-catalog",
        action="approve.command",
        target=command_id,
        outcome=outcome,
        correlation_id=correlation_id,
        evidence_ref=f"config/command-catalog.json#commands.{command_id}",
    )
    emit_event_best_effort(event, context=f"command approval '{command_id}'", stderr=sys.stderr)


def build_approval_policy_input(
    *,
    command_catalog: dict,
    workflow_catalog: dict,
    command_id: str,
    requester_class: str,
    approver_classes: list[str],
    preflight_passed: bool,
    validation_passed: bool,
    receipt_planned: bool,
    self_approve: bool,
    break_glass: bool,
) -> dict[str, object]:
    contract = command_catalog["commands"].get(command_id)
    if contract is None:
        raise ValueError(f"Unknown command contract: {command_id}")

    workflow = workflow_catalog["workflows"][contract["workflow_id"]]
    policy = command_catalog["approval_policies"][contract["approval_policy"]]
    return {
        "command_id": command_id,
        "requester_class": requester_class,
        "approver_classes": approver_classes,
        "preflight_passed": preflight_passed,
        "validation_passed": validation_passed,
        "receipt_planned": receipt_planned,
        "self_approve": self_approve,
        "break_glass": break_glass,
        "contract": contract,
        "workflow": workflow,
        "policy": policy,
    }


def evaluate_approval(
    command_catalog: dict,
    workflow_catalog: dict,
    command_id: str,
    requester_class: str,
    approver_classes: list[str],
    *,
    preflight_passed: bool,
    validation_passed: bool,
    receipt_planned: bool,
    self_approve: bool,
    break_glass: bool,
) -> dict[str, object]:
    contract = command_catalog["commands"].get(command_id)
    if contract is None:
        raise ValueError(f"Unknown command contract: {command_id}")
    workflow = workflow_catalog["workflows"][contract["workflow_id"]]
    payload = build_approval_policy_input(
        command_catalog=command_catalog,
        workflow_catalog=workflow_catalog,
        command_id=command_id,
        requester_class=requester_class,
        approver_classes=approver_classes,
        preflight_passed=preflight_passed,
        validation_passed=validation_passed,
        receipt_planned=receipt_planned,
        self_approve=self_approve,
        break_glass=break_glass,
    )
    decision = evaluate_command_approval_policy(payload, repo_root=Path(__file__).resolve().parents[1])
    entrypoint_target = workflow["preferred_entrypoint"].get("target")
    return {
        "approved": bool(decision["approved"]),
        "reasons": list(decision["reasons"]),
        "workflow_id": str(decision["workflow_id"]),
        "entrypoint": str(decision["entrypoint"]),
        "entrypoint_target": str(entrypoint_target) if entrypoint_target is not None else None,
        "receipt_required": bool(decision["receipt_required"]),
    }


def check_approval(
    command_catalog: dict,
    workflow_catalog: dict,
    command_id: str,
    requester_class: str,
    approver_classes: list[str],
    *,
    preflight_passed: bool,
    validation_passed: bool,
    receipt_planned: bool,
    self_approve: bool,
    break_glass: bool,
    audit_correlation_id: str | None,
    audit_actor_id: str | None,
) -> int:
    try:
        verdict = evaluate_approval(
            command_catalog,
            workflow_catalog,
            command_id,
            requester_class,
            approver_classes,
            preflight_passed=preflight_passed,
            validation_passed=validation_passed,
            receipt_planned=receipt_planned,
            self_approve=self_approve,
            break_glass=break_glass,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if verdict["reasons"]:
        print(f"Command approval REJECTED: {command_id}")
        for reason in verdict["reasons"]:
            print(f"  - {reason}")
        emit_approval_audit_event(
            command_id=command_id,
            requester_class=requester_class,
            outcome="rejected",
            correlation_id=audit_correlation_id,
            actor_id=audit_actor_id,
        )
        return 1

    print(f"Command approval OK: {command_id}")
    print(f"  requester_class: {requester_class}")
    print(f"  approver_classes: {', '.join(approver_classes) if approver_classes else 'none'}")
    print(f"  workflow: {verdict['workflow_id']}")
    print(f"  entrypoint: {verdict['entrypoint']}")
    print(f"  receipt_required: {verdict['receipt_required']}")
    emit_approval_audit_event(
        command_id=command_id,
        requester_class=requester_class,
        outcome="success",
        correlation_id=audit_correlation_id,
        actor_id=audit_actor_id,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect, validate, or evaluate approval for the command catalog.")
    parser.add_argument("--list", action="store_true", help="List available command contracts.")
    parser.add_argument("--command", help="Show one command contract.")
    parser.add_argument("--validate", action="store_true", help="Validate the command catalog.")
    parser.add_argument(
        "--check-approval",
        action="store_true",
        help="Evaluate the approval policy for one command contract.",
    )
    parser.add_argument("--requester-class", help="Identity class that is requesting execution.")
    parser.add_argument(
        "--approver-classes",
        default="",
        help="Comma-separated approver identity classes.",
    )
    parser.add_argument(
        "--preflight-passed",
        action="store_true",
        help="Mark the controller-local preflight requirement as satisfied.",
    )
    parser.add_argument(
        "--validation-passed",
        action="store_true",
        help="Mark repository validation as satisfied.",
    )
    parser.add_argument(
        "--receipt-planned",
        action="store_true",
        help="Mark live-apply receipt planning as satisfied.",
    )
    parser.add_argument(
        "--self-approve",
        action="store_true",
        help="Indicate that the requester is also counted as an approver.",
    )
    parser.add_argument(
        "--break-glass",
        action="store_true",
        help="Indicate that the request is attempting break-glass execution.",
    )
    parser.add_argument("--audit-correlation-id", help="Override the mutation audit correlation id.")
    parser.add_argument("--audit-actor-id", help="Override the mutation audit actor id.")
    args = parser.parse_args()

    try:
        secret_manifest = load_secret_manifest()
        validate_secret_manifest(secret_manifest)
        workflow_catalog = load_workflow_catalog()
        validate_workflow_catalog(workflow_catalog, secret_manifest)
        if CORRECTION_LOOP_CATALOG_PATH.exists():
            correction_catalog = load_correction_loop_catalog()
            validate_correction_loop_catalog(correction_catalog, workflow_catalog)
        command_catalog = load_command_catalog()
        validate_command_catalog(command_catalog, workflow_catalog, secret_manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Command catalog", exc)

    if args.validate:
        print(f"Command catalog OK: {COMMAND_CATALOG_PATH}")
        return 0

    if args.check_approval:
        if not args.command:
            print("--check-approval requires --command", file=sys.stderr)
            return 2
        if not args.requester_class:
            print("--check-approval requires --requester-class", file=sys.stderr)
            return 2
        return check_approval(
            command_catalog,
            workflow_catalog,
            args.command,
            args.requester_class,
            split_csv(args.approver_classes),
            preflight_passed=args.preflight_passed,
            validation_passed=args.validation_passed,
            receipt_planned=args.receipt_planned,
            self_approve=args.self_approve,
            break_glass=args.break_glass,
            audit_correlation_id=args.audit_correlation_id,
            audit_actor_id=args.audit_actor_id,
        )

    if args.command:
        return show_command(command_catalog, workflow_catalog, args.command)

    return list_commands(command_catalog, workflow_catalog)


if __name__ == "__main__":
    sys.exit(main())
