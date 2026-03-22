#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def validate_manifest(manifest: dict) -> None:
    secrets = manifest.get("secrets", {})
    workflows = manifest.get("workflows", {})

    if not isinstance(secrets, dict) or not isinstance(workflows, dict):
        raise ValueError("manifest must define object-valued 'secrets' and 'workflows'")

    for workflow_id, workflow in workflows.items():
        for field in ("required_secret_ids", "generated_secret_ids", "blocked_secret_ids"):
            for secret_id in workflow.get(field, []):
                if secret_id not in secrets:
                    raise ValueError(
                        f"workflow '{workflow_id}' references unknown secret '{secret_id}' in '{field}'"
                    )


def list_workflows(manifest: dict) -> int:
    print(f"Manifest: {MANIFEST_PATH}")
    print("Available workflows:")
    for workflow_id, workflow in sorted(manifest["workflows"].items()):
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


def report_generated(manifest: dict, workflow: dict) -> None:
    for secret_id in workflow.get("generated_secret_ids", []):
        secret = manifest["secrets"][secret_id]
        if secret["kind"] == "file":
            path = Path(secret["path"]).expanduser()
            state = "present" if path.is_file() and path.stat().st_size > 0 else "absent"
            print(f"INFO generated {secret_id}: {state} at {path}")
        elif secret["kind"] == "env":
            name = secret["name"]
            state = "set" if os.environ.get(name, "").strip() else "unset"
            print(f"INFO generated {secret_id}: {state} in {name}")


def run_workflow(manifest: dict, workflow_id: str) -> int:
    workflow = manifest["workflows"].get(workflow_id)
    if workflow is None:
        print(f"Unknown workflow: {workflow_id}", file=sys.stderr)
        return 2

    print(f"Preflight workflow: {workflow_id}")
    print(f"Description: {workflow['description']}")

    failed = False

    for secret_id in workflow.get("required_secret_ids", []):
        ok, message = check_secret(secret_id, manifest["secrets"][secret_id])
        print(message)
        if not ok:
            failed = True

    for secret_id in workflow.get("blocked_secret_ids", []):
        ok, message = check_secret(secret_id, manifest["secrets"][secret_id])
        print(message)
        if not ok:
            failed = True

    report_generated(manifest, workflow)

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
        manifest = load_manifest()
        validate_manifest(manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Manifest error: {exc}", file=sys.stderr)
        return 2

    if args.list or not args.workflow:
        return list_workflows(manifest)

    return run_workflow(manifest, args.workflow)


if __name__ == "__main__":
    sys.exit(main())
