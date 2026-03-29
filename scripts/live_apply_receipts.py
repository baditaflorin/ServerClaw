#!/usr/bin/env python3

import argparse
import json
import os
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
from environment_catalog import receipt_environment_ids, receipt_subdirectory_environments
from workflow_catalog import load_workflow_catalog, load_secret_manifest, validate_secret_manifest, validate_workflow_catalog


SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COMMIT_HASH_PATTERN = re.compile(r"^[0-9a-f]{7,64}$")
LEGACY_WORKFLOW_ID_PATTERN = re.compile(r"^adr-\d{4}-[a-z0-9-]+-live-apply$")
ALLOWED_RESULTS = {"pass", "partial", "fail"}
ALLOWED_SMOKE_SUITE_STATUSES = {"passed", "failed", "skipped"}
ALLOWED_ENVIRONMENTS = set(receipt_environment_ids())
ALLOWED_CORRECTION_LOOP_DIAGNOSES = {
    "transient_failure",
    "contract_drift",
    "dependency_outage",
    "stale_input",
    "irreversible_data_loss_risk",
}


def load_receipt(path: Path) -> dict:
    return load_json(path)


def git_commit_exists(commit: str) -> bool:
    return command_succeeds(["git", "rev-parse", "--verify", f"{commit}^{{commit}}"])


def git_metadata_available() -> bool:
    return (REPO_ROOT / ".git").exists() and command_succeeds(
        ["git", "rev-parse", "--is-inside-work-tree"]
    )


def git_commit_lookup_available() -> bool:
    if not git_metadata_available():
        return False
    return command_succeeds(["git", "cat-file", "-e", "HEAD^{commit}"])


def validate_source_commit(commit: str, path: Path) -> None:
    if git_commit_lookup_available():
        if not git_commit_exists(commit):
            raise ValueError(f"{path.name}: source_commit '{commit}' is not a valid git commit")
        return

    if not COMMIT_HASH_PATTERN.fullmatch(commit):
        raise ValueError(
            f"{path.name}: source_commit '{commit}' must look like a git commit hash when .git metadata is unavailable"
        )


def iter_receipt_paths() -> list[Path]:
    return sorted(RECEIPTS_DIR.rglob("*.json"))


def receipt_environment_for_path(path: Path) -> str:
    relative = path.relative_to(RECEIPTS_DIR)
    return relative.parts[0] if relative.parts and relative.parts[0] in receipt_subdirectory_environments() else "production"


def receipt_relative_path(path: Path) -> Path:
    return path.relative_to(REPO_ROOT)


def resolve_receipt_path(receipt_ref: str) -> Path:
    candidate = Path(receipt_ref)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def receipt_id_with_session(base_receipt_id: str, session_suffix: str | None = None) -> str:
    suffix = session_suffix or os.environ.get("LV3_SESSION_RECEIPT_SUFFIX", "").strip()
    normalized_suffix = re.sub(r"[^a-z0-9-]+", "-", suffix.lower()).strip("-")
    if not normalized_suffix:
        return base_receipt_id
    if base_receipt_id.endswith(f"-{normalized_suffix}"):
        return base_receipt_id
    return f"{base_receipt_id}-{normalized_suffix}"


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

    recorded_at = receipt.get("recorded_at")
    if recorded_at is not None:
        if not isinstance(recorded_at, str) or not recorded_at.strip():
            raise ValueError(f"{path.name}: recorded_at must be a non-empty ISO-8601 string when present")

    if not SEMVER_PATTERN.match(receipt["repo_version_context"]):
        raise ValueError(f"{path.name}: repo_version_context must use semantic version format")

    environment = receipt.get("environment", receipt_environment_for_path(path))
    if not isinstance(environment, str) or environment not in ALLOWED_ENVIRONMENTS:
        raise ValueError(f"{path.name}: environment must be one of {sorted(ALLOWED_ENVIRONMENTS)}")
    derived_environment = receipt_environment_for_path(path)
    if environment != derived_environment:
        raise ValueError(
            f"{path.name}: environment '{environment}' does not match receipt path environment '{derived_environment}'"
        )

    if (
        receipt["workflow_id"] not in workflow_catalog["workflows"]
        and not LEGACY_WORKFLOW_ID_PATTERN.fullmatch(receipt["workflow_id"])
    ):
        raise ValueError(
            f"{path.name}: workflow_id '{receipt['workflow_id']}' is not in {WORKFLOW_CATALOG_PATH.name}"
        )

    validate_source_commit(receipt["source_commit"], path)

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

    smoke_suites = receipt.get("smoke_suites")
    if smoke_suites is not None:
        if not isinstance(smoke_suites, list) or not smoke_suites:
            raise ValueError(f"{path.name}: smoke_suites must be a non-empty list when present")
        seen_suite_ids: set[str] = set()
        for item in smoke_suites:
            if not isinstance(item, dict):
                raise ValueError(f"{path.name}: smoke_suites entries must be objects")
            for field in ("suite_id", "service_id", "environment", "status", "executed_at", "summary"):
                if not isinstance(item.get(field), str) or not item[field]:
                    raise ValueError(f"{path.name}: smoke_suites field '{field}' is required")
            if item["status"] not in ALLOWED_SMOKE_SUITE_STATUSES:
                raise ValueError(
                    f"{path.name}: smoke_suites status '{item['status']}' must be one of {sorted(ALLOWED_SMOKE_SUITE_STATUSES)}"
                )
            if item["environment"] not in ALLOWED_ENVIRONMENTS:
                raise ValueError(
                    f"{path.name}: smoke_suites environment '{item['environment']}' must be one of {sorted(ALLOWED_ENVIRONMENTS)}"
                )
            if item["suite_id"] in seen_suite_ids:
                raise ValueError(f"{path.name}: smoke_suites must not repeat suite_id '{item['suite_id']}'")
            seen_suite_ids.add(item["suite_id"])
            report_ref = item.get("report_ref")
            if report_ref is not None:
                if not isinstance(report_ref, str) or not report_ref.strip():
                    raise ValueError(f"{path.name}: smoke_suites report_ref must be a non-empty string when present")
                if not (REPO_ROOT / report_ref).exists():
                    raise ValueError(f"{path.name}: smoke_suites report ref '{report_ref}' does not exist")

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

    correction_loop = receipt.get("correction_loop")
    if correction_loop is not None:
        if not isinstance(correction_loop, dict):
            raise ValueError(f"{path.name}: correction_loop must be an object when present")
        for field in ("loop_id", "surface", "repair_action", "verification"):
            value = correction_loop.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{path.name}: correction_loop.{field} must be a non-empty string")
        diagnosis = correction_loop.get("diagnosis")
        if diagnosis is not None:
            if not isinstance(diagnosis, str) or diagnosis not in ALLOWED_CORRECTION_LOOP_DIAGNOSES:
                raise ValueError(
                    f"{path.name}: correction_loop.diagnosis must be one of {sorted(ALLOWED_CORRECTION_LOOP_DIAGNOSES)}"
                )


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
        environment = receipt.get("environment", receipt_environment_for_path(path))
        print(
            f"  - {receipt['receipt_id']}: {receipt['recorded_on']} [{environment}] {receipt['workflow_id']} "
            f"applied {receipt['applied_on']} "
            f"{receipt['source_commit'][:7]} {receipt['summary']}"
        )
    return 0


def show_receipt(receipt_id: str) -> int:
    matches = [path for path in iter_receipt_paths() if path.stem == receipt_id]
    if not matches:
        print(f"Unknown receipt: {receipt_id}", file=sys.stderr)
        return 2
    if len(matches) > 1:
        print(
            f"Ambiguous receipt id '{receipt_id}': "
            + ", ".join(str(receipt_relative_path(path)) for path in matches),
            file=sys.stderr,
        )
        return 2

    target_path = matches[0]

    receipt = load_receipt(target_path)
    print(f"Receipt: {receipt['receipt_id']}")
    print(f"Path: {receipt_relative_path(target_path)}")
    print(f"Environment: {receipt.get('environment', receipt_environment_for_path(target_path))}")
    print(f"Applied on: {receipt['applied_on']}")
    print(f"Recorded on: {receipt['recorded_on']}")
    if receipt.get("recorded_at"):
        print(f"Recorded at: {receipt['recorded_at']}")
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
    if receipt.get("smoke_suites"):
        print("Smoke suites:")
        for item in receipt["smoke_suites"]:
            report_suffix = f" ({item['report_ref']})" if item.get("report_ref") else ""
            print(
                f"  - [{item['status']}] {item['suite_id']} "
                f"{item['service_id']}@{item['environment']}: {item['summary']}{report_suffix}"
            )
    print("Evidence refs:")
    for ref in receipt["evidence_refs"]:
        print(f"  - {ref}")
    correction_loop = receipt.get("correction_loop")
    if isinstance(correction_loop, dict):
        print("Correction loop:")
        print(f"  - loop_id: {correction_loop['loop_id']}")
        print(f"  - surface: {correction_loop['surface']}")
        if correction_loop.get("diagnosis"):
            print(f"  - diagnosis: {correction_loop['diagnosis']}")
        print(f"  - repair_action: {correction_loop['repair_action']}")
        print(f"  - verification: {correction_loop['verification']}")
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
