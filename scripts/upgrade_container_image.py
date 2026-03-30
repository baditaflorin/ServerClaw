#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from container_image_policy import (
    IMAGE_CATALOG_PATH,
    IMAGE_SCAN_RECEIPTS_DIR,
    load_image_catalog,
    resolve_remote_digest,
    validate_image_catalog,
)
from controller_automation_toolkit import emit_cli_error, write_json


TRIVY_IMAGE = "docker.io/aquasec/trivy:0.63.0"
TRIVY_CACHE_DIR = IMAGE_CATALOG_PATH.parent.parent / ".cache" / "trivy"


def build_ref(registry_ref: str, tag: str, digest: str) -> str:
    return f"{registry_ref}:{tag}@{digest}"


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def scan_image(image_ref: str, image_id: str, scanned_on: str) -> tuple[dict, Path]:
    receipt_path = IMAGE_SCAN_RECEIPTS_DIR / f"{scanned_on}-{image_id.replace('_', '-')}.json"
    raw_path = receipt_path.with_suffix(".trivy.json")
    TRIVY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_SCAN_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{TRIVY_CACHE_DIR}:/root/.cache/",
        "-v",
        f"{IMAGE_SCAN_RECEIPTS_DIR}:/work",
        TRIVY_IMAGE,
        "image",
        "--scanners",
        "vuln",
        "--skip-version-check",
        "--severity",
        "CRITICAL,HIGH",
        "--format",
        "json",
        "--output",
        f"/work/{raw_path.name}",
        image_ref,
    ]
    result = run_command(command)
    if result.returncode != 0:
        raise ValueError(f"trivy scan failed for {image_ref}: {result.stderr.strip() or result.stdout.strip()}")

    raw_payload = json.loads(raw_path.read_text())
    critical = 0
    high = 0
    targets_with_findings = []
    for item in raw_payload.get("Results", []):
        vulnerabilities = item.get("Vulnerabilities", []) or []
        target_critical = sum(1 for vuln in vulnerabilities if vuln.get("Severity") == "CRITICAL")
        target_high = sum(1 for vuln in vulnerabilities if vuln.get("Severity") == "HIGH")
        critical += target_critical
        high += target_high
        if target_critical or target_high:
            targets_with_findings.append(
                {
                    "target": item.get("Target"),
                    "class": item.get("Class"),
                    "type": item.get("Type"),
                    "critical": target_critical,
                    "high": target_high,
                }
            )

    receipt = {
        "schema_version": "1.0.0",
        "image_id": image_id,
        "image_ref": image_ref,
        "scanner": "trivy",
        "scanner_image": TRIVY_IMAGE,
        "scanned_on": scanned_on,
        "summary": {"critical": critical, "high": high},
        "targets_with_findings": targets_with_findings,
        "raw_report": str(raw_path.relative_to(IMAGE_CATALOG_PATH.parent.parent)),
    }
    return receipt, receipt_path


def update_catalog(
    catalog: dict,
    *,
    image_id: str,
    tag: str,
    digest: str,
    scanned_on: str,
    receipt_path: Path,
    exception: dict | None,
) -> dict:
    entry = catalog["images"][image_id]
    entry["tag"] = tag
    entry["digest"] = digest
    entry["ref"] = build_ref(entry["registry_ref"], tag, digest)
    entry["pinned_on"] = scanned_on
    entry["scan_receipt"] = str(receipt_path.relative_to(IMAGE_CATALOG_PATH.parent.parent))
    if exception is None:
        entry["scan_status"] = "pass_no_critical"
        entry.pop("exception", None)
    else:
        entry["scan_status"] = "exception_open"
        entry["exception"] = exception
    return catalog


def maybe_apply(apply_targets: list[str]) -> list[dict]:
    results = []
    repo_root = IMAGE_CATALOG_PATH.parent.parent
    for target in apply_targets:
        command = ["make", target]
        result = run_command(command, cwd=repo_root)
        results.append(
            {
                "target": target,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        )
        if result.returncode != 0:
            raise ValueError(f"apply target '{target}' failed")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upgrade one managed image by resolving a new digest, scanning it, and updating the catalog."
    )
    parser.add_argument("--image-id", required=True, help="Catalog image id to upgrade.")
    parser.add_argument("--tag", help="Override tag instead of reusing the catalog tag.")
    parser.add_argument("--apply", action="store_true", help="Run the catalog apply_targets after updating the catalog.")
    parser.add_argument("--write", action="store_true", help="Persist the updated catalog and scan receipt.")
    parser.add_argument("--exception-justification", help="Justification for allowing a digest with open vulnerability budget exceptions.")
    parser.add_argument("--exception-reason", help="Deprecated alias for --exception-justification.")
    parser.add_argument("--exception-owner", help="Owner of the critical-finding exception.")
    parser.add_argument("--exception-expires-on", help="YYYY-MM-DD expiry date for the active exception.")
    parser.add_argument("--exception-review-by", help="Deprecated alias for --exception-expires-on.")
    parser.add_argument(
        "--exception-control",
        action="append",
        default=[],
        help="Compensating control for the active exception. Repeat for multiple controls.",
    )
    parser.add_argument(
        "--exception-controls-json",
        help="JSON array of compensating controls for the active exception.",
    )
    parser.add_argument(
        "--exception-remediation-plan",
        help="Explicit remediation plan for clearing the active exception before expiry.",
    )
    args = parser.parse_args()

    try:
        catalog = load_image_catalog()
        validate_image_catalog(catalog)
        if args.image_id not in catalog["images"]:
            raise ValueError(f"unknown image id '{args.image_id}'")

        scanned_on = dt.date.today().isoformat()
        entry = catalog["images"][args.image_id]
        tag = args.tag or entry["tag"]
        digest = resolve_remote_digest(entry["registry_ref"], tag, entry["platform"])
        image_ref = build_ref(entry["registry_ref"], tag, digest)
        receipt, receipt_path = scan_image(image_ref, args.image_id, scanned_on)
        exception = None
        if receipt["summary"]["critical"] != 0:
            justification = args.exception_justification or args.exception_reason
            expires_on = args.exception_expires_on or args.exception_review_by
            controls = list(args.exception_control)
            if args.exception_controls_json:
                controls.extend(json.loads(args.exception_controls_json))
            if not (
                justification
                and args.exception_owner
                and expires_on
                and controls
                and args.exception_remediation_plan
            ):
                raise ValueError(
                    f"{image_ref} has {receipt['summary']['critical']} critical vulnerabilities; "
                    "provide --exception-justification, --exception-owner, --exception-expires-on, "
                    "--exception-control or --exception-controls-json, and --exception-remediation-plan to allow it"
                )
            exception = {
                "justification": justification,
                "owner": args.exception_owner,
                "compensating_controls": controls,
                "approved_on": scanned_on,
                "expires_on": expires_on,
                "remediation_plan": args.exception_remediation_plan,
            }

        apply_results = []
        updated_catalog = update_catalog(
            catalog,
            image_id=args.image_id,
            tag=tag,
            digest=digest,
            scanned_on=scanned_on,
            receipt_path=receipt_path,
            exception=exception,
        )

        if args.write:
            write_json(receipt_path, receipt)
            validate_image_catalog(updated_catalog)
            write_json(IMAGE_CATALOG_PATH, updated_catalog)
            if args.apply:
                apply_results = maybe_apply(entry["apply_targets"])

        print(
            json.dumps(
                {
                    "image_id": args.image_id,
                    "image_ref": image_ref,
                    "write": args.write,
                    "apply": args.apply,
                    "scan_receipt": str(receipt_path.relative_to(IMAGE_CATALOG_PATH.parent.parent)),
                    "summary": receipt["summary"],
                    "exception": exception,
                    "apply_results": apply_results,
                },
                indent=2,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Upgrade container image", exc)


if __name__ == "__main__":
    sys.exit(main())
