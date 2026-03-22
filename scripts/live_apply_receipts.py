#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

from controller_automation_toolkit import (
    RECEIPTS_DIR,
    REPO_ROOT,
    WORKFLOW_CATALOG_PATH,
    command_succeeds,
    emit_cli_error,
    load_json,
)
from workflow_catalog import load_workflow_catalog, load_secret_manifest, validate_secret_manifest, validate_workflow_catalog


SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALLOWED_RESULTS = {"pass", "partial", "fail"}


def load_receipt(path: Path) -> dict:
    return load_json(path)


def git_commit_exists(commit: str) -> bool:
    return command_succeeds(["git", "rev-parse", "--verify", f"{commit}^{{commit}}"])


def iter_receipt_paths() -> list[Path]:
    return sorted(RECEIPTS_DIR.glob("*.json"))


def validate_receipt(receipt: dict, path: Path, workflow_catalog: dict) -> None:
    required_string_fields = (
        "schema_version",
        "receipt_id",
        "applied_on",
        "recorded_on",
        "recorded_by",
        "source_commit",
        "repo_version_context",
        "workflow_id",
        "adr",
        "summary",
    )
    for field in required_string_fields:
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path.name}: missing or invalid string field '{field}'")

    if receipt["schema_version"] != "1.0.0":
        raise ValueError(f"{path.name}: unsupported schema_version '{receipt['schema_version']}'")

    if path.stem != receipt["receipt_id"]:
        raise ValueError(f"{path.name}: filename must match receipt_id '{receipt['receipt_id']}'")

    for field in ("applied_on", "recorded_on"):
        if not DATE_PATTERN.match(receipt[field]):
            raise ValueError(f"{path.name}: {field} must use YYYY-MM-DD")

    if not SEMVER_PATTERN.match(receipt["repo_version_context"]):
        raise ValueError(f"{path.name}: repo_version_context must use semantic version format")

    if receipt["workflow_id"] not in workflow_catalog["workflows"]:
        raise ValueError(
            f"{path.name}: workflow_id '{receipt['workflow_id']}' is not in {WORKFLOW_CATALOG_PATH.name}"
        )

    if not git_commit_exists(receipt["source_commit"]):
        raise ValueError(f"{path.name}: source_commit '{receipt['source_commit']}' is not a valid git commit")

    targets = receipt.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError(f"{path.name}: targets must be a non-empty list")
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError(f"{path.name}: each target must be an object")
        if not isinstance(target.get("kind"), str) or not target["kind"]:
            raise ValueError(f"{path.name}: target.kind is required")
        if not isinstance(target.get("name"), str) or not target["name"]:
            raise ValueError(f"{path.name}: target.name is required")

    verification = receipt.get("verification")
    if not isinstance(verification, list) or not verification:
        raise ValueError(f"{path.name}: verification must be a non-empty list")
    for item in verification:
        if not isinstance(item, dict):
            raise ValueError(f"{path.name}: verification entries must be objects")
        for field in ("check", "result", "observed"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ValueError(f"{path.name}: verification field '{field}' is required")
        if item["result"] not in ALLOWED_RESULTS:
            raise ValueError(
                f"{path.name}: verification result '{item['result']}' must be one of {sorted(ALLOWED_RESULTS)}"
            )

    evidence_refs = receipt.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise ValueError(f"{path.name}: evidence_refs must be a non-empty list")
    for ref in evidence_refs:
        if not isinstance(ref, str) or not ref:
            raise ValueError(f"{path.name}: evidence_refs entries must be non-empty strings")
        if not (REPO_ROOT / ref).exists():
            raise ValueError(f"{path.name}: evidence ref '{ref}' does not exist")

    notes = receipt.get("notes")
    if not isinstance(notes, list):
        raise ValueError(f"{path.name}: notes must be a list")
    for note in notes:
        if not isinstance(note, str) or not note:
            raise ValueError(f"{path.name}: notes entries must be non-empty strings")


def validate_receipts() -> int:
    secret_manifest = load_secret_manifest()
    validate_secret_manifest(secret_manifest)
    workflow_catalog = load_workflow_catalog()
    validate_workflow_catalog(workflow_catalog, secret_manifest)

    receipt_paths = iter_receipt_paths()
    if not receipt_paths:
        raise ValueError(f"no receipt files found in {RECEIPTS_DIR}")

    seen_ids: set[str] = set()
    for path in receipt_paths:
        receipt = load_receipt(path)
        validate_receipt(receipt, path, workflow_catalog)
        receipt_id = receipt["receipt_id"]
        if receipt_id in seen_ids:
            raise ValueError(f"duplicate receipt_id '{receipt_id}'")
        seen_ids.add(receipt_id)

    print(f"Live apply receipts OK: {RECEIPTS_DIR}")
    return 0


def list_receipts() -> int:
    secret_manifest = load_secret_manifest()
    validate_secret_manifest(secret_manifest)
    workflow_catalog = load_workflow_catalog()
    validate_workflow_catalog(workflow_catalog, secret_manifest)

    print(f"Receipt directory: {RECEIPTS_DIR}")
    print("Available receipts:")
    for path in iter_receipt_paths():
        receipt = load_receipt(path)
        print(
            f"  - {receipt['receipt_id']}: {receipt['recorded_on']} {receipt['workflow_id']} "
            f"applied {receipt['applied_on']} "
            f"{receipt['source_commit'][:7]} {receipt['summary']}"
        )
    return 0


def show_receipt(receipt_id: str) -> int:
    target_path = RECEIPTS_DIR / f"{receipt_id}.json"
    if not target_path.is_file():
        print(f"Unknown receipt: {receipt_id}", file=sys.stderr)
        return 2

    receipt = load_receipt(target_path)
    print(f"Receipt: {receipt['receipt_id']}")
    print(f"Applied on: {receipt['applied_on']}")
    print(f"Recorded on: {receipt['recorded_on']}")
    print(f"Recorded by: {receipt['recorded_by']}")
    print(f"Source commit: {receipt['source_commit']}")
    print(f"Repo version context: {receipt['repo_version_context']}")
    print(f"Workflow: {receipt['workflow_id']}")
    print(f"ADR: {receipt['adr']}")
    print(f"Summary: {receipt['summary']}")
    print("Targets:")
    for target in receipt["targets"]:
        extras = []
        for field in ("vmid", "address"):
            value = target.get(field)
            if value:
                extras.append(f"{field}={value}")
        extras_text = f" ({', '.join(extras)})" if extras else ""
        print(f"  - {target['kind']}: {target['name']}{extras_text}")
    print("Verification:")
    for item in receipt["verification"]:
        print(f"  - [{item['result']}] {item['check']}: {item['observed']}")
    print("Evidence refs:")
    for ref in receipt["evidence_refs"]:
        print(f"  - {ref}")
    if receipt["notes"]:
        print("Notes:")
        for note in receipt["notes"]:
            print(f"  - {note}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or validate structured live-apply receipts."
    )
    parser.add_argument("--validate", action="store_true", help="Validate all receipts.")
    parser.add_argument("--list", action="store_true", help="List receipts.")
    parser.add_argument("--receipt", help="Show one receipt by receipt_id.")
    args = parser.parse_args()

    try:
        if args.validate:
            return validate_receipts()
        if args.receipt:
            return show_receipt(args.receipt)
        return list_receipts()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Live apply receipt", exc)


if __name__ == "__main__":
    sys.exit(main())
