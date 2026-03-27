#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path

from controller_automation_toolkit import (
    SECRET_MANIFEST_PATH as MANIFEST_PATH,
    WORKFLOW_CATALOG_PATH,
    emit_cli_error,
)
from workflow_catalog import (
    WORKFLOW_SECRET_FIELDS,
    load_secret_manifest,
    load_workflow_catalog,
    validate_secret_manifest,
    validate_workflow_catalog,
)


def list_workflows(catalog: dict) -> int:
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"Workflow catalog: {WORKFLOW_CATALOG_PATH}")
    print("Available preflight workflows:")
    for workflow_id, workflow in sorted(catalog["workflows"].items()):
        if not workflow["preflight"]["required"]:
            continue
        print(f"  - {workflow_id}: {workflow['description']}")
    return 0


def check_secret(secret_id: str, secret: dict) -> tuple[bool, str]:
    kind = secret["kind"]
    status = secret["status"]

    if status == "blocked":
        reason = secret.get("blocked_reason", "workflow is intentionally blocked")
        return False, f"BLOCKED {secret_id}: {reason}"

    if kind == "file":
        path = Path(secret["path"]).expanduser()
        if path.is_file() and path.stat().st_size > 0:
            return True, f"PASS file {secret_id}: {path}"
        return False, f"FAIL file {secret_id}: missing or empty at {path}"

    if kind == "env":
        name = secret["name"]
        if os.environ.get(name, "").strip():
            return True, f"PASS env {secret_id}: {name} is set"
        return False, f"FAIL env {secret_id}: {name} is not set"

    return False, f"FAIL {secret_id}: unsupported secret kind {kind}"


def report_generated(secret_manifest: dict, workflow: dict) -> None:
    for secret_id in workflow["preflight"].get("generated_secret_ids", []):
        secret = secret_manifest["secrets"][secret_id]
        if secret["kind"] == "file":
            path = Path(secret["path"]).expanduser()
            state = "present" if path.is_file() and path.stat().st_size > 0 else "absent"
            print(f"INFO generated {secret_id}: {state} at {path}")
        elif secret["kind"] == "env":
            name = secret["name"]
            state = "set" if os.environ.get(name, "").strip() else "unset"
            print(f"INFO generated {secret_id}: {state} in {name}")


def run_workflow(secret_manifest: dict, catalog: dict, workflow_id: str) -> int:
    workflow = catalog["workflows"].get(workflow_id)
    if workflow is None:
        print(f"Unknown workflow: {workflow_id}", file=sys.stderr)
        return 2

    print(f"Preflight workflow: {workflow_id}")
    print(f"Description: {workflow['description']}")

    failed = False
    preflight = workflow["preflight"]

    if not preflight["required"]:
        print("INFO no controller-local secret preflight required for this workflow")

    for secret_id in preflight.get("required_secret_ids", []):
        ok, message = check_secret(secret_id, secret_manifest["secrets"][secret_id])
        print(message)
        if not ok:
            failed = True

    for secret_id in preflight.get("blocked_secret_ids", []):
        ok, message = check_secret(secret_id, secret_manifest["secrets"][secret_id])
        print(message)
        if not ok:
            failed = True

    report_generated(secret_manifest, workflow)

    if failed:
        print(f"Result: FAIL ({workflow_id})", file=sys.stderr)
        return 1

    print(f"Result: PASS ({workflow_id})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check controller-local secret prerequisites for a workflow."
    )
    parser.add_argument("--workflow", help="Workflow id from the controller-local secret manifest.")
    parser.add_argument("--list", action="store_true", help="List available workflows.")
    args = parser.parse_args()

    try:
        secret_manifest = load_secret_manifest()
        validate_secret_manifest(secret_manifest)
        catalog = load_workflow_catalog()
        validate_workflow_catalog(catalog, secret_manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Manifest", exc)

    if args.list or not args.workflow:
        return list_workflows(catalog)

    return run_workflow(secret_manifest, catalog, args.workflow)


if __name__ == "__main__":
    sys.exit(main())
