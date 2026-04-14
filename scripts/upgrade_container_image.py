#!/usr/bin/env python3

from __future__ import annotations

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
from controller_automation_toolkit import emit_cli_error, repo_path, shared_repo_root, write_json
from sbom_scanner import (
    CVE_RECEIPTS_DIR,
    SBOM_RECEIPTS_DIR,
    DEFAULT_GRYPE_DB_CACHE_DIR,
    DEFAULT_SYFT_CACHE_DIR,
    load_scanner_config,
    now_utc,
    relpath,
    scan_catalog_image,
)


DEFAULT_WORKING_ROOT = repo_path(".local", "image-upgrade-scans")


def catalog_repo_root() -> Path:
    return shared_repo_root(IMAGE_CATALOG_PATH.parent.parent)


def explicit_exception_requested(args: argparse.Namespace) -> bool:
    return any(
        (
            args.exception_justification,
            args.exception_reason,
            args.exception_owner,
            args.exception_expires_on,
            args.exception_review_by,
            args.exception_control,
            args.exception_controls_json,
            args.exception_remediation_plan,
        )
    )


def renew_exception_window(exception: dict, *, scanned_on: str) -> dict:
    renewed = dict(exception)
    approved_on = dt.date.fromisoformat(str(exception["approved_on"]))
    expiry_key = "expires_on" if exception.get("expires_on") is not None else "review_by"
    expires_on = dt.date.fromisoformat(str(exception[expiry_key]))
    window_days = max(1, (expires_on - approved_on).days)
    new_approved = dt.date.fromisoformat(scanned_on)
    renewed["approved_on"] = scanned_on
    renewed[expiry_key] = (new_approved + dt.timedelta(days=window_days)).isoformat()
    return renewed


def build_ref(registry_ref: str, tag: str, digest: str) -> str:
    return f"{registry_ref}:{tag}@{digest}"


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def image_receipt_name(image_id: str, scanned_on: str) -> str:
    return f"{scanned_on}-{image_id.replace('_', '-')}.json"


def build_scan_receipt(
    *,
    image_id: str,
    image_ref: str,
    scanned_on: str,
    scanner_config: dict,
    sbom_path: Path,
    cve_path: Path,
    cve_receipt: dict,
) -> dict:
    return {
        "schema_version": "1.0.0",
        "image_id": image_id,
        "image_ref": image_ref,
        "scanner": "grype",
        "scanner_image": scanner_config["grype"]["container_image"],
        "sbom_generator_image": scanner_config["syft"]["container_image"],
        "scanned_on": scanned_on,
        "sbom_receipt": relpath(sbom_path),
        "cve_receipt": relpath(cve_path),
        "summary": cve_receipt["summary"],
    }


def update_catalog(
    catalog: dict,
    *,
    image_id: str,
    tag: str,
    digest: str,
    scanned_on: str,
    receipt_path: Path,
    exception: dict | None,
    preserve_pin: bool = False,
) -> dict:
    entry = catalog["images"][image_id]
    if not preserve_pin:
        entry["tag"] = tag
        entry["digest"] = digest
        entry["ref"] = build_ref(entry["registry_ref"], tag, digest)
        entry["pinned_on"] = scanned_on
    entry["scan_receipt"] = str(receipt_path.relative_to(catalog_repo_root()))
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
    parser.add_argument(
        "--refresh-scan-only",
        action="store_true",
        help=(
            "Re-scan the currently pinned digest and refresh scan receipts without changing "
            "the catalog tag, digest, ref, or pinned_on date."
        ),
    )
    parser.add_argument(
        "--renew-existing-exception",
        action="store_true",
        help=(
            "When --refresh-scan-only encounters critical findings and the catalog already has an "
            "exception, renew that exception by shifting its existing approval window forward."
        ),
    )
    parser.add_argument(
        "--apply", action="store_true", help="Run the catalog apply_targets after updating the catalog."
    )
    parser.add_argument("--write", action="store_true", help="Persist the updated catalog and scan receipt.")
    parser.add_argument(
        "--exception-justification",
        help="Justification for allowing a digest with open vulnerability budget exceptions.",
    )
    parser.add_argument("--exception-reason", help="Deprecated alias for --exception-justification.")
    parser.add_argument("--working-root", type=Path, default=DEFAULT_WORKING_ROOT)
    parser.add_argument("--skip-db-update", action="store_true")
    parser.add_argument("--skip-artifact-cache", action="store_true")
    parser.add_argument("--syft-cache-dir", type=Path, default=DEFAULT_SYFT_CACHE_DIR)
    parser.add_argument("--grype-db-cache-dir", type=Path, default=DEFAULT_GRYPE_DB_CACHE_DIR)
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
        if args.apply and not args.write:
            raise ValueError("--apply requires --write so the updated catalog is persisted before converge targets run")
        if args.refresh_scan_only and args.tag:
            raise ValueError("--tag cannot be combined with --refresh-scan-only")
        if args.renew_existing_exception and not args.refresh_scan_only:
            raise ValueError("--renew-existing-exception requires --refresh-scan-only")

        catalog = load_image_catalog()
        validate_image_catalog(catalog)
        if args.image_id not in catalog["images"]:
            raise ValueError(f"unknown image id '{args.image_id}'")

        scanner_config = load_scanner_config()
        scanned_at = now_utc()
        scanned_on = scanned_at.date().isoformat()
        entry = catalog["images"][args.image_id]
        if args.refresh_scan_only:
            tag = entry["tag"]
            digest = entry["digest"]
            image_ref = entry["ref"]
        else:
            tag = args.tag or entry["tag"]
            digest = resolve_remote_digest(entry["registry_ref"], tag, entry["platform"])
            image_ref = build_ref(entry["registry_ref"], tag, digest)

        if args.write:
            sbom_dir = SBOM_RECEIPTS_DIR
            cve_dir = CVE_RECEIPTS_DIR
            receipt_path = IMAGE_SCAN_RECEIPTS_DIR / image_receipt_name(args.image_id, scanned_on)
        else:
            working_root = args.working_root / args.image_id
            sbom_dir = working_root / "sbom"
            cve_dir = working_root / "cve"
            receipt_path = working_root / image_receipt_name(args.image_id, scanned_on)

        sbom_path, cve_path, cve_receipt = scan_catalog_image(
            image_id=args.image_id,
            image_ref=image_ref,
            runtime_host=entry.get("runtime_host"),
            platform_name=entry["platform"],
            sbom_dir=sbom_dir,
            cve_dir=cve_dir,
            config=scanner_config,
            scanned_at=scanned_at,
            syft_cache_dir=args.syft_cache_dir,
            grype_db_cache_dir=args.grype_db_cache_dir,
            update_grype_db=not args.skip_db_update,
            use_artifact_cache=not args.skip_artifact_cache,
        )
        receipt = build_scan_receipt(
            image_id=args.image_id,
            image_ref=image_ref,
            scanned_on=scanned_on,
            scanner_config=scanner_config,
            sbom_path=sbom_path,
            cve_path=cve_path,
            cve_receipt=cve_receipt,
        )
        write_json(receipt_path, receipt)

        blocking_findings = receipt["summary"]["blocking_findings_with_fix"]
        if blocking_findings != 0:
            raise ValueError(
                f"{image_ref} has {blocking_findings} HIGH/CRITICAL findings with an available fix; "
                "choose a different digest before updating the managed catalog"
            )

        exception = None
        if receipt["summary"]["critical"] != 0:
            if explicit_exception_requested(args):
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
            elif args.refresh_scan_only and isinstance(entry.get("exception"), dict):
                exception = dict(entry["exception"])
                if args.renew_existing_exception:
                    exception = renew_exception_window(exception, scanned_on=scanned_on)
            else:
                raise ValueError(
                    f"{image_ref} has {receipt['summary']['critical']} critical vulnerabilities; "
                    "provide --exception-justification, --exception-owner, --exception-expires-on, "
                    "--exception-control or --exception-controls-json, and --exception-remediation-plan to allow it"
                )

        apply_results = []
        updated_catalog = update_catalog(
            catalog,
            image_id=args.image_id,
            tag=tag,
            digest=digest,
            scanned_on=scanned_on,
            receipt_path=receipt_path,
            exception=exception,
            preserve_pin=args.refresh_scan_only,
        )

        if args.write:
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
                    "refresh_scan_only": args.refresh_scan_only,
                    "scan_receipt": relpath(receipt_path),
                    "sbom_receipt": relpath(sbom_path),
                    "cve_receipt": relpath(cve_path),
                    "summary": receipt["summary"],
                    "exception": exception,
                    "apply_results": apply_results,
                },
                indent=2,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Upgrade container image", exc)


if __name__ == "__main__":
    sys.exit(main())
