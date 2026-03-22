#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
SECRET_MANIFEST_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
MAKEFILE_PATH = REPO_ROOT / "Makefile"

ALLOWED_ENTRYPOINT_KINDS = {"make_target"}
ALLOWED_LIVE_IMPACTS = {
    "repo_only",
    "host_live",
    "guest_live",
    "host_and_guest_live",
    "external_live",
}
ALLOWED_LIFECYCLE_STATUSES = {"active", "blocked"}
WORKFLOW_SECRET_FIELDS = ("required_secret_ids", "generated_secret_ids", "blocked_secret_ids")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_secret_manifest() -> dict:
    return load_json(SECRET_MANIFEST_PATH)


def load_workflow_catalog() -> dict:
    return load_json(WORKFLOW_CATALOG_PATH)


def parse_make_targets() -> set[str]:
    targets = set()
    pattern = re.compile(r"^([A-Za-z0-9_-]+):")

    for line in MAKEFILE_PATH.read_text().splitlines():
        match = pattern.match(line)
        if not match:
            continue
        target = match.group(1)
        if target != ".PHONY":
            targets.add(target)

    return targets


def validate_secret_manifest(manifest: dict) -> None:
    secrets = manifest.get("secrets")
    if not isinstance(secrets, dict):
        raise ValueError("secret manifest must define an object-valued 'secrets' key")


def validate_workflow_catalog(catalog: dict, secret_manifest: dict) -> None:
    workflows = catalog.get("workflows")
    secrets = secret_manifest["secrets"]
    make_targets = parse_make_targets()

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
        print(f"  - {workflow_id} [{status}, {impact}]: {command}")
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
    print(f"Entrypoint: {workflow['preferred_entrypoint']['command']}")
    print(f"Runbook: {workflow['owner_runbook']}")
    print("Validation targets:")
    for target in workflow["validation_targets"]:
        print(f"  - make {target}")

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
        print(f"Workflow catalog error: {exc}", file=sys.stderr)
        return 2

    if args.validate:
        print(f"Workflow catalog OK: {WORKFLOW_CATALOG_PATH}")
        return 0

    if args.workflow:
        return show_workflow(catalog, args.workflow)

    return list_workflows(catalog)


if __name__ == "__main__":
    sys.exit(main())
