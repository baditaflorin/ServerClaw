#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

from controller_automation_toolkit import (
    REPO_ROOT,
    SECRET_MANIFEST_PATH,
    WORKFLOW_CATALOG_PATH,
    emit_cli_error,
    load_json,
    load_yaml,
    parse_make_targets,
)

ALLOWED_ENTRYPOINT_KINDS = {"make_target"}
ALLOWED_LIVE_IMPACTS = {
    "repo_only",
    "host_live",
    "guest_live",
    "host_and_guest_live",
    "external_live",
}
ALLOWED_LIFECYCLE_STATUSES = {"active", "blocked"}
ALLOWED_EXECUTION_CLASSES = {"mutation", "diagnostic"}
ALLOWED_ESCALATION_ACTIONS = {"notify_and_abort", "abort_silently", "escalate_to_operator"}
ALLOWED_RESOURCE_CLAIM_ACCESS = {"read", "write", "exclusive"}
WORKFLOW_SECRET_FIELDS = ("required_secret_ids", "generated_secret_ids", "blocked_secret_ids")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_secret_manifest() -> dict:
    return load_json(SECRET_MANIFEST_PATH)


def load_workflow_catalog() -> dict:
    return load_json(WORKFLOW_CATALOG_PATH)


def load_workflow_defaults() -> dict:
    return load_yaml(REPO_ROOT / "config" / "workflow-defaults.yaml")


def validate_budget_payload(payload: dict, workflow_id: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"workflow '{workflow_id}' budget must be a mapping")
    required_int_fields = (
        "max_duration_seconds",
        "max_steps",
        "max_concurrent_instances",
        "max_touched_hosts",
        "max_restarts",
        "max_rollback_depth",
    )
    for field in required_int_fields:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"workflow '{workflow_id}' budget field '{field}' must be an integer")
        if value < 0:
            raise ValueError(f"workflow '{workflow_id}' budget field '{field}' must be >= 0")
    if payload["max_duration_seconds"] < 1:
        raise ValueError(f"workflow '{workflow_id}' budget field 'max_duration_seconds' must be >= 1")
    if payload["max_steps"] < 1:
        raise ValueError(f"workflow '{workflow_id}' budget field 'max_steps' must be >= 1")
    if payload["max_concurrent_instances"] < 1:
        raise ValueError(f"workflow '{workflow_id}' budget field 'max_concurrent_instances' must be >= 1")
    escalation_action = payload.get("escalation_action")
    if escalation_action not in ALLOWED_ESCALATION_ACTIONS:
        raise ValueError(
            f"workflow '{workflow_id}' budget escalation_action must be one of {sorted(ALLOWED_ESCALATION_ACTIONS)}"
        )


def validate_resource_claims(payload: object, workflow_id: str) -> None:
    if payload is None:
        return
    if not isinstance(payload, list):
        raise ValueError(f"workflow '{workflow_id}' resource_claims must be a list")
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"workflow '{workflow_id}' resource_claims[{index}] must be a mapping")
        resource = item.get("resource")
        access = item.get("access")
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError(f"workflow '{workflow_id}' resource_claims[{index}].resource must be a non-empty string")
        if access not in ALLOWED_RESOURCE_CLAIM_ACCESS:
            raise ValueError(
                f"workflow '{workflow_id}' resource_claims[{index}].access must be one of {sorted(ALLOWED_RESOURCE_CLAIM_ACCESS)}"
            )


def validate_secret_manifest(manifest: dict) -> None:
    secrets = manifest.get("secrets")
    if not isinstance(secrets, dict):
        raise ValueError("secret manifest must define an object-valued 'secrets' key")


def validate_workflow_catalog(catalog: dict, secret_manifest: dict) -> None:
    workflows = catalog.get("workflows")
    secrets = secret_manifest["secrets"]
    make_targets = parse_make_targets()
    defaults_payload = load_workflow_defaults().get("default_budget")
    if not isinstance(defaults_payload, dict):
        raise ValueError("config/workflow-defaults.yaml must define default_budget")
    validate_budget_payload(defaults_payload, "default_budget")

    if not isinstance(workflows, dict):
        raise ValueError("workflow catalog must define an object-valued 'workflows' key")

    for workflow_id, workflow in workflows.items():
        if not isinstance(workflow.get("description"), str) or not workflow["description"].strip():
            raise ValueError(f"workflow '{workflow_id}' must define a non-empty description")

        lifecycle_status = workflow.get("lifecycle_status")
        if lifecycle_status not in ALLOWED_LIFECYCLE_STATUSES:
            raise ValueError(
                f"workflow '{workflow_id}' has invalid lifecycle_status '{lifecycle_status}'"
            )

        execution_class = workflow.get("execution_class", "mutation")
        if execution_class not in ALLOWED_EXECUTION_CLASSES:
            raise ValueError(
                f"workflow '{workflow_id}' has invalid execution_class '{execution_class}'"
            )
        dedup_window = workflow.get("dedup_window_seconds")
        if dedup_window is not None and (isinstance(dedup_window, bool) or not isinstance(dedup_window, int) or dedup_window < 0):
            raise ValueError(f"workflow '{workflow_id}' dedup_window_seconds must be an integer >= 0")
        validate_resource_claims(workflow.get("resource_claims"), workflow_id)

        budget = dict(defaults_payload)
        workflow_budget = workflow.get("budget", {})
        if workflow_budget is None:
            workflow_budget = {}
        if not isinstance(workflow_budget, dict):
            raise ValueError(f"workflow '{workflow_id}' budget must be a mapping")
        budget.update(workflow_budget)
        validate_budget_payload(budget, workflow_id)

        preferred_entrypoint = workflow.get("preferred_entrypoint")
        if not isinstance(preferred_entrypoint, dict):
            raise ValueError(f"workflow '{workflow_id}' must define preferred_entrypoint")

        entrypoint_kind = preferred_entrypoint.get("kind")
        if entrypoint_kind not in ALLOWED_ENTRYPOINT_KINDS:
            raise ValueError(
                f"workflow '{workflow_id}' has unsupported entrypoint kind '{entrypoint_kind}'"
            )

        if entrypoint_kind == "make_target":
            target = preferred_entrypoint.get("target")
            command = preferred_entrypoint.get("command")
            if not isinstance(target, str) or not target:
                raise ValueError(f"workflow '{workflow_id}' make_target entrypoint needs target")
            if target not in make_targets:
                raise ValueError(
                    f"workflow '{workflow_id}' references unknown Make target '{target}'"
                )
            if not isinstance(command, str) or not command.strip():
                raise ValueError(
                    f"workflow '{workflow_id}' make_target entrypoint needs a command string"
                )

        preflight = workflow.get("preflight")
        if not isinstance(preflight, dict):
            raise ValueError(f"workflow '{workflow_id}' must define a preflight object")

        if not isinstance(preflight.get("required"), bool):
            raise ValueError(f"workflow '{workflow_id}' preflight.required must be boolean")

        for field in WORKFLOW_SECRET_FIELDS:
            secret_ids = preflight.get(field, [])
            if not isinstance(secret_ids, list):
                raise ValueError(f"workflow '{workflow_id}' field '{field}' must be a list")
            for secret_id in secret_ids:
                if secret_id not in secrets:
                    raise ValueError(
                        f"workflow '{workflow_id}' references unknown secret '{secret_id}'"
                    )

        validation_targets = workflow.get("validation_targets")
        if not isinstance(validation_targets, list):
            raise ValueError(f"workflow '{workflow_id}' must define validation_targets as a list")
        for target in validation_targets:
            if target not in make_targets:
                raise ValueError(
                    f"workflow '{workflow_id}' references unknown validation target '{target}'"
                )

        live_impact = workflow.get("live_impact")
        if live_impact not in ALLOWED_LIVE_IMPACTS:
            raise ValueError(f"workflow '{workflow_id}' has invalid live_impact '{live_impact}'")

        owner_runbook = workflow.get("owner_runbook")
        if not isinstance(owner_runbook, str) or not owner_runbook:
            raise ValueError(f"workflow '{workflow_id}' must define owner_runbook")
        if not (REPO_ROOT / owner_runbook).is_file():
            raise ValueError(
                f"workflow '{workflow_id}' references missing owner_runbook '{owner_runbook}'"
            )

        implementation_refs = workflow.get("implementation_refs")
        if not isinstance(implementation_refs, list) or not implementation_refs:
            raise ValueError(
                f"workflow '{workflow_id}' must define a non-empty implementation_refs list"
            )
        for path_str in implementation_refs:
            if not (REPO_ROOT / path_str).exists():
                raise ValueError(
                    f"workflow '{workflow_id}' references missing implementation path '{path_str}'"
                )

        outputs = workflow.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            raise ValueError(f"workflow '{workflow_id}' must define a non-empty outputs list")

        verification_commands = workflow.get("verification_commands")
        if not isinstance(verification_commands, list) or not verification_commands:
            raise ValueError(
                f"workflow '{workflow_id}' must define a non-empty verification_commands list"
            )


def list_workflows(catalog: dict) -> int:
    print(f"Workflow catalog: {WORKFLOW_CATALOG_PATH}")
    print("Available workflows:")
    for workflow_id, workflow in sorted(catalog["workflows"].items()):
        command = workflow["preferred_entrypoint"]["command"]
        impact = workflow["live_impact"]
        status = workflow["lifecycle_status"]
        execution_class = workflow.get("execution_class", "mutation")
        print(f"  - {workflow_id} [{status}, {impact}, {execution_class}]: {command}")
    return 0


def show_workflow(catalog: dict, workflow_id: str) -> int:
    workflow = catalog["workflows"].get(workflow_id)
    if workflow is None:
        print(f"Unknown workflow: {workflow_id}", file=sys.stderr)
        return 2

    print(f"Workflow: {workflow_id}")
    print(f"Description: {workflow['description']}")
    print(f"Lifecycle: {workflow['lifecycle_status']}")
    print(f"Live impact: {workflow['live_impact']}")
    print(f"Execution class: {workflow.get('execution_class', 'mutation')}")
    print(f"Dedup window: {workflow.get('dedup_window_seconds', 'default')}")
    print(f"Entrypoint: {workflow['preferred_entrypoint']['command']}")
    print(f"Runbook: {workflow['owner_runbook']}")
    print("Budget:")
    defaults = load_workflow_defaults().get("default_budget", {})
    budget = dict(defaults if isinstance(defaults, dict) else {})
    workflow_budget = workflow.get("budget", {})
    if isinstance(workflow_budget, dict):
        budget.update(workflow_budget)
    for key, value in budget.items():
        print(f"  - {key}: {value}")
    print("Validation targets:")
    for target in workflow["validation_targets"]:
        print(f"  - make {target}")

    claims = workflow.get("resource_claims", [])
    if claims:
        print("Resource claims:")
        for claim in claims:
            print(f"  - {claim['resource']} ({claim['access']})")

    preflight = workflow["preflight"]
    if preflight["required"]:
        print("Preflight secrets:")
        for field in WORKFLOW_SECRET_FIELDS:
            for secret_id in preflight.get(field, []):
                print(f"  - {field}: {secret_id}")
    else:
        print("Preflight secrets: none")

    print("Implementation refs:")
    for path_str in workflow["implementation_refs"]:
        print(f"  - {path_str}")

    print("Outputs:")
    for output in workflow["outputs"]:
        print(f"  - {output}")

    print("Verification commands:")
    for command in workflow["verification_commands"]:
        print(f"  - {command}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or validate the repository workflow execution catalog."
    )
    parser.add_argument("--list", action="store_true", help="List available workflows.")
    parser.add_argument("--workflow", help="Show one workflow from the catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the workflow catalog.")
    args = parser.parse_args()

    try:
        secret_manifest = load_secret_manifest()
        validate_secret_manifest(secret_manifest)
        catalog = load_workflow_catalog()
        validate_workflow_catalog(catalog, secret_manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Workflow catalog", exc)

    if args.validate:
        print(f"Workflow catalog OK: {WORKFLOW_CATALOG_PATH}")
        return 0

    if args.workflow:
        return show_workflow(catalog, args.workflow)

    return list_workflows(catalog)


if __name__ == "__main__":
    sys.exit(main())
