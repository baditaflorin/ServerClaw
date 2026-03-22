#!/usr/bin/env python3

import argparse
import json
import sys
from typing import Final

from controller_automation_toolkit import emit_cli_error, load_json, repo_path
from workflow_catalog import (
    ALLOWED_LIVE_IMPACTS,
    load_secret_manifest,
    load_workflow_catalog,
    validate_secret_manifest,
    validate_workflow_catalog,
)


COMMAND_CATALOG_PATH = repo_path("config", "command-catalog.json")
SUPPORTED_SCHEMA_VERSION: Final[str] = "1.0.0"
ALLOWED_IDENTITY_CLASSES = {"human_operator", "service_identity", "agent", "break_glass"}
ALLOWED_SCOPES = {"proxmox_host", "guest_runtime", "host_and_guest", "external_service"}


def load_command_catalog() -> dict:
    return load_json(COMMAND_CATALOG_PATH)


def require_str(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def require_list(value: object, path: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_mapping(value: object, path: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_int(value: object, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


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
        raise ValueError(
            f"command catalog must declare schema_version '{SUPPORTED_SCHEMA_VERSION}'"
        )

    workflows = workflow_catalog["workflows"]
    secret_ids = set(secret_manifest["secrets"].keys())

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
        require_int(policy.get("minimum_approvals"), f"approval_policies.{policy_id}.minimum_approvals", 1)
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
            raise ValueError(
                f"commands.{command_id}.workflow_id references unknown workflow '{workflow_id}'"
            )
        workflow = workflows[workflow_id]
        covered_workflow_ids.add(workflow_id)
        live_impact = workflow["live_impact"]
        if live_impact not in ALLOWED_LIVE_IMPACTS or live_impact == "repo_only":
            raise ValueError(
                f"commands.{command_id}.workflow_id must reference a mutating non-repo-only workflow"
            )

        scope = require_str(contract.get("scope"), f"commands.{command_id}.scope")
        if scope not in ALLOWED_SCOPES:
            raise ValueError(f"commands.{command_id}.scope must be one of {sorted(ALLOWED_SCOPES)}")

        approval_policy = require_str(
            contract.get("approval_policy"), f"commands.{command_id}.approval_policy"
        )
        if approval_policy not in policies:
            raise ValueError(
                f"commands.{command_id}.approval_policy references unknown policy '{approval_policy}'"
            )

        inputs = require_list(contract.get("inputs"), f"commands.{command_id}.inputs")
        if not inputs:
            raise ValueError(f"commands.{command_id}.inputs must not be empty")
        for index, item in enumerate(inputs):
            item = require_mapping(item, f"commands.{command_id}.inputs[{index}]")
            require_str(item.get("name"), f"commands.{command_id}.inputs[{index}].name")
            kind = require_str(item.get("kind"), f"commands.{command_id}.inputs[{index}].kind")
            require_bool(item.get("required"), f"commands.{command_id}.inputs[{index}].required")
            require_str(item.get("source"), f"commands.{command_id}.inputs[{index}].source")
            require_str(
                item.get("description"), f"commands.{command_id}.inputs[{index}].description"
            )
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

        failure_guidance = require_mapping(
            contract.get("failure_guidance"), f"commands.{command_id}.failure_guidance"
        )
        for field in ("stop_conditions", "rollback_guidance"):
            items = require_list(
                failure_guidance.get(field), f"commands.{command_id}.failure_guidance.{field}"
            )
            if not items:
                raise ValueError(f"commands.{command_id}.failure_guidance.{field} must not be empty")
            for index, item in enumerate(items):
                require_str(item, f"commands.{command_id}.failure_guidance.{field}[{index}]")

    missing_contracts = sorted(
        workflow_id
        for workflow_id, workflow in workflows.items()
        if workflow["live_impact"] != "repo_only" and workflow_id not in covered_workflow_ids
    )
    if missing_contracts:
        raise ValueError(
            "command catalog is missing contracts for mutating workflows: "
            + ", ".join(missing_contracts)
        )


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
    return 0


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
) -> int:
    contract = command_catalog["commands"].get(command_id)
    if contract is None:
        print(f"Unknown command contract: {command_id}", file=sys.stderr)
        return 2

    workflow = workflow_catalog["workflows"][contract["workflow_id"]]
    policy = command_catalog["approval_policies"][contract["approval_policy"]]
    reasons = []

    if workflow["lifecycle_status"] != "active":
        reasons.append(
            f"workflow '{contract['workflow_id']}' is '{workflow['lifecycle_status']}', not active"
        )

    if requester_class not in ALLOWED_IDENTITY_CLASSES:
        reasons.append(f"requester_class must be one of {sorted(ALLOWED_IDENTITY_CLASSES)}")
    elif requester_class not in policy["allowed_requester_classes"]:
        reasons.append(
            f"requester_class '{requester_class}' is not allowed by policy '{contract['approval_policy']}'"
        )

    if len(approver_classes) < policy["minimum_approvals"]:
        reasons.append(
            f"policy '{contract['approval_policy']}' requires at least {policy['minimum_approvals']} approval(s)"
        )

    for approver_class in approver_classes:
        if approver_class not in ALLOWED_IDENTITY_CLASSES:
            reasons.append(f"approver_class '{approver_class}' must be one of {sorted(ALLOWED_IDENTITY_CLASSES)}")
        elif approver_class not in policy["allowed_approver_classes"]:
            reasons.append(
                f"approver_class '{approver_class}' is not allowed by policy '{contract['approval_policy']}'"
            )

    if self_approve and not policy["allow_self_approval"]:
        reasons.append(f"policy '{contract['approval_policy']}' does not allow self approval")
    if break_glass and not policy["allow_break_glass"]:
        reasons.append(f"policy '{contract['approval_policy']}' does not allow break-glass execution")
    if policy["require_preflight"] and not preflight_passed:
        reasons.append("preflight has not been marked passed")
    if policy["require_validation"] and not validation_passed:
        reasons.append("repository validation has not been marked passed")
    if policy["require_receipt_plan"] and not receipt_planned:
        reasons.append("receipt planning has not been marked complete")

    if reasons:
        print(f"Command approval REJECTED: {command_id}")
        for reason in reasons:
            print(f"  - {reason}")
        return 1

    print(f"Command approval OK: {command_id}")
    print(f"  requester_class: {requester_class}")
    print(f"  approver_classes: {', '.join(approver_classes) if approver_classes else 'none'}")
    print(f"  workflow: {contract['workflow_id']}")
    print(f"  entrypoint: {workflow['preferred_entrypoint']['command']}")
    print(f"  receipt_required: {contract['evidence']['live_apply_receipt_required']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect, validate, or evaluate approval for the command catalog."
    )
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
    args = parser.parse_args()

    try:
        secret_manifest = load_secret_manifest()
        validate_secret_manifest(secret_manifest)
        workflow_catalog = load_workflow_catalog()
        validate_workflow_catalog(workflow_catalog, secret_manifest)
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
        )

    if args.command:
        return show_command(command_catalog, workflow_catalog, args.command)

    return list_commands(command_catalog, workflow_catalog)


if __name__ == "__main__":
    sys.exit(main())
