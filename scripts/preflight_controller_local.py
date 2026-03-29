#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from controller_automation_toolkit import (
    REPO_ROOT,
    SECRET_MANIFEST_PATH as MANIFEST_PATH,
    WORKFLOW_CATALOG_PATH,
    emit_cli_error,
    resolve_repo_local_path,
)
from worktree_bootstrap import (
    WORKTREE_BOOTSTRAP_MANIFEST_PATH,
    load_bootstrap_catalog,
    resolve_entry_path,
    resolve_workflow_manifest_ids,
    validate_bootstrap_catalog,
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
    print(f"Bootstrap catalog: {WORKTREE_BOOTSTRAP_MANIFEST_PATH}")
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
        path = resolve_repo_local_path(secret["path"], repo_root=REPO_ROOT)
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
            path = resolve_repo_local_path(secret["path"], repo_root=REPO_ROOT)
            state = "present" if path.is_file() and path.stat().st_size > 0 else "absent"
            print(f"INFO generated {secret_id}: {state} at {path}")
        elif secret["kind"] == "env":
            name = secret["name"]
            state = "set" if os.environ.get(name, "").strip() else "unset"
            print(f"INFO generated {secret_id}: {state} in {name}")


def _path_is_ready(path: Path, kind: str) -> bool:
    if kind == "directory":
        return path.is_dir()
    return path.is_file() and path.stat().st_size > 0


def check_bootstrap_input(entry: dict) -> tuple[bool, str]:
    entry_id = entry["id"]
    kind = entry["kind"]
    if kind == "env":
        name = entry["name"]
        if os.environ.get(name, "").strip():
            return True, f"PASS bootstrap input {entry_id}: env {name} is set"
        return False, f"FAIL bootstrap input {entry_id}: env {name} is not set"

    path = resolve_entry_path(entry, repo_root=REPO_ROOT)
    if _path_is_ready(path, kind):
        return True, f"PASS bootstrap input {entry_id}: {kind} present at {path}"
    return False, f"FAIL bootstrap input {entry_id}: missing {kind} at {path}"


def ensure_generated_artifact(entry: dict) -> tuple[bool, str]:
    entry_id = entry["id"]
    path = resolve_entry_path(entry, repo_root=REPO_ROOT)
    kind = entry["kind"]
    if _path_is_ready(path, kind):
        return True, f"PASS bootstrap artifact {entry_id}: {kind} present at {path}"

    command = entry["materialize_command"]
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        shell=True,
        executable="/bin/bash",
        env=os.environ.copy(),
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        detail = detail.splitlines()[-1]
        return (
            False,
            f"FAIL bootstrap artifact {entry_id}: `{command}` exited {completed.returncode} ({detail})",
        )
    if _path_is_ready(path, kind):
        return True, f"PASS bootstrap artifact {entry_id}: materialized {kind} at {path} via `{command}`"
    return False, f"FAIL bootstrap artifact {entry_id}: `{command}` completed but {kind} is still missing at {path}"


def report_optional_cache(entry: dict) -> str:
    entry_id = entry["id"]
    kind = entry["kind"]
    if kind == "env":
        name = entry["name"]
        state = "set" if os.environ.get(name, "").strip() else "unset"
        return f"INFO bootstrap cache {entry_id}: {state} in {name}"
    path = resolve_entry_path(entry, repo_root=REPO_ROOT)
    state = "present" if _path_is_ready(path, kind) else "absent"
    return f"INFO bootstrap cache {entry_id}: {state} at {path}"


def run_bootstrap_preflight(bootstrap_catalog: dict, workflow: dict) -> bool:
    manifest_ids = resolve_workflow_manifest_ids(bootstrap_catalog, workflow)
    if not manifest_ids:
        print("INFO no bootstrap manifest configured for this workflow")
        return False

    failed = False
    for manifest_id in manifest_ids:
        manifest = bootstrap_catalog["manifests"][manifest_id]
        print(f"Bootstrap manifest: {manifest_id}")
        print(f"Bootstrap description: {manifest['description']}")
        for entry in manifest.get("generated_artifacts", []):
            ok, message = ensure_generated_artifact(entry)
            print(message)
            if not ok:
                failed = True
        for entry in manifest.get("required_local_inputs", []):
            ok, message = check_bootstrap_input(entry)
            print(message)
            if not ok:
                failed = True
        for entry in manifest.get("optional_read_only_caches", []):
            print(report_optional_cache(entry))
    return failed


def run_workflow(secret_manifest: dict, catalog: dict, bootstrap_catalog: dict, workflow_id: str) -> int:
    workflow = catalog["workflows"].get(workflow_id)
    if workflow is None:
        print(f"Unknown workflow: {workflow_id}", file=sys.stderr)
        return 2

    print(f"Preflight workflow: {workflow_id}")
    print(f"Description: {workflow['description']}")

    failed = run_bootstrap_preflight(bootstrap_catalog, workflow)
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
        bootstrap_catalog = load_bootstrap_catalog()
        validate_bootstrap_catalog(bootstrap_catalog)
        validate_workflow_catalog(catalog, secret_manifest, bootstrap_catalog)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Manifest", exc)

    if args.list or not args.workflow:
        return list_workflows(catalog)

    return run_workflow(secret_manifest, catalog, bootstrap_catalog, args.workflow)


if __name__ == "__main__":
    sys.exit(main())
