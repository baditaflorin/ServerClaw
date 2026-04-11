#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_int, require_list, require_mapping, require_str

CATALOG_PATH = REPO_ROOT / "config" / "repo-deploy-base-image-profiles.json"
SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "repo-deploy-base-image-profiles.schema.json"
SUPPORTED_SCHEMA_VERSION = "1.0.0"
SUPPORTED_DEPLOYMENT_LANES = {"coolify"}
SUPPORTED_BUILD_PACKS = {"dockercompose", "dockerfile", "nixpacks", "static"}
SUPPORTED_BUNDLE_CONCERNS = {
    "common_infrastructure",
    "language_build",
    "runtime_base",
    "stateful_service",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.UTC)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_identifier(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not value[0].islower():
        raise ValueError(f"{path} must start with a lowercase letter")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if any(char not in allowed for char in value):
        raise ValueError(f"{path} must use lowercase letters, numbers, or hyphens")
    return value


def load_profile_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    payload = load_json(path)
    return require_mapping(payload, str(path))


def validate_profile_catalog(payload: dict[str, Any], *, path: Path = CATALOG_PATH) -> None:
    path_str = str(path)
    if payload.get("$schema") != "docs/schema/repo-deploy-base-image-profiles.schema.json":
        raise ValueError(
            "config/repo-deploy-base-image-profiles.json.$schema must reference docs/schema/repo-deploy-base-image-profiles.schema.json"
        )
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"config/repo-deploy-base-image-profiles.json.schema_version must be {SUPPORTED_SCHEMA_VERSION}"
        )

    profiles = require_list(payload.get("profiles"), f"{path_str}.profiles")
    if not profiles:
        raise ValueError(f"{path_str}.profiles must not be empty")

    profile_ids: set[str] = set()
    for profile_index, raw_profile in enumerate(profiles):
        profile_path = f"{path_str}.profiles[{profile_index}]"
        profile = require_mapping(raw_profile, profile_path)
        profile_id = require_identifier(profile.get("id"), f"{profile_path}.id")
        if profile_id in profile_ids:
            raise ValueError(f"{profile_path}.id duplicates '{profile_id}'")
        profile_ids.add(profile_id)

        require_str(profile.get("name"), f"{profile_path}.name")
        require_str(profile.get("description"), f"{profile_path}.description")

        deployment_lane = require_str(profile.get("deployment_lane"), f"{profile_path}.deployment_lane")
        if deployment_lane not in SUPPORTED_DEPLOYMENT_LANES:
            raise ValueError(f"{profile_path}.deployment_lane must be one of {sorted(SUPPORTED_DEPLOYMENT_LANES)}")

        build_packs = require_list(profile.get("allowed_build_packs"), f"{profile_path}.allowed_build_packs")
        if not build_packs:
            raise ValueError(f"{profile_path}.allowed_build_packs must not be empty")
        for build_pack_index, build_pack in enumerate(build_packs):
            build_pack = require_str(
                build_pack,
                f"{profile_path}.allowed_build_packs[{build_pack_index}]",
            )
            if build_pack not in SUPPORTED_BUILD_PACKS:
                raise ValueError(
                    f"{profile_path}.allowed_build_packs[{build_pack_index}] must be one of {sorted(SUPPORTED_BUILD_PACKS)}"
                )

        require_int(profile.get("freshness_hours"), f"{profile_path}.freshness_hours", minimum=1)

        repository_ids: set[str] = set()
        for repository_index, raw_repository in enumerate(profile.get("repositories", [])):
            repository_path = f"{profile_path}.repositories[{repository_index}]"
            repository = require_mapping(raw_repository, repository_path)
            repository_id = require_identifier(repository.get("id"), f"{repository_path}.id")
            if repository_id in repository_ids:
                raise ValueError(f"{repository_path}.id duplicates '{repository_id}'")
            repository_ids.add(repository_id)
            require_str(repository.get("repo"), f"{repository_path}.repo")
            require_str(repository.get("branch"), f"{repository_path}.branch")
            require_str(repository.get("notes"), f"{repository_path}.notes")

        bundles = require_list(profile.get("bundles"), f"{profile_path}.bundles")
        if not bundles:
            raise ValueError(f"{profile_path}.bundles must not be empty")

        bundle_ids: set[str] = set()
        for bundle_index, raw_bundle in enumerate(bundles):
            bundle_path = f"{profile_path}.bundles[{bundle_index}]"
            bundle = require_mapping(raw_bundle, bundle_path)
            bundle_id = require_identifier(bundle.get("id"), f"{bundle_path}.id")
            if bundle_id in bundle_ids:
                raise ValueError(f"{bundle_path}.id duplicates '{bundle_id}'")
            bundle_ids.add(bundle_id)

            concern = require_str(bundle.get("concern"), f"{bundle_path}.concern")
            if concern not in SUPPORTED_BUNDLE_CONCERNS:
                raise ValueError(f"{bundle_path}.concern must be one of {sorted(SUPPORTED_BUNDLE_CONCERNS)}")

            images = require_list(bundle.get("images"), f"{bundle_path}.images")
            if not images:
                raise ValueError(f"{bundle_path}.images must not be empty")

            image_ids: set[str] = set()
            refs: set[str] = set()
            for image_index, raw_image in enumerate(images):
                image_path = f"{bundle_path}.images[{image_index}]"
                image = require_mapping(raw_image, image_path)
                image_id = require_identifier(image.get("id"), f"{image_path}.id")
                if image_id in image_ids:
                    raise ValueError(f"{image_path}.id duplicates '{image_id}'")
                image_ids.add(image_id)
                ref = require_str(image.get("ref"), f"{image_path}.ref")
                if ref in refs:
                    raise ValueError(f"{image_path}.ref duplicates '{ref}' inside {bundle_path}")
                refs.add(ref)


def build_plan(payload: dict[str, Any]) -> dict[str, Any]:
    validate_profile_catalog(payload)

    entries_by_ref: dict[str, dict[str, Any]] = {}
    profiles_summary: list[dict[str, Any]] = []
    for raw_profile in payload["profiles"]:
        profile = require_mapping(raw_profile, "profile")
        profile_id = str(profile["id"])
        freshness_hours = int(profile["freshness_hours"])
        bundle_ids: list[str] = []
        profiles_summary.append(
            {
                "id": profile_id,
                "deployment_lane": profile["deployment_lane"],
                "allowed_build_packs": list(profile["allowed_build_packs"]),
                "freshness_hours": freshness_hours,
                "bundle_ids": [bundle["id"] for bundle in profile["bundles"]],
            }
        )
        for raw_bundle in profile["bundles"]:
            bundle = require_mapping(raw_bundle, f"profile {profile_id} bundle")
            bundle_id = str(bundle["id"])
            bundle_ids.append(bundle_id)
            concern = str(bundle["concern"])
            for raw_image in bundle["images"]:
                image = require_mapping(raw_image, f"profile {profile_id} bundle {bundle_id} image")
                ref = str(image["ref"])
                entry = entries_by_ref.setdefault(
                    ref,
                    {
                        "ref": ref,
                        "image_ids": [],
                        "profile_ids": [],
                        "bundle_ids": [],
                        "concerns": [],
                        "freshness_hours": freshness_hours,
                    },
                )
                if image["id"] not in entry["image_ids"]:
                    entry["image_ids"].append(image["id"])
                if profile_id not in entry["profile_ids"]:
                    entry["profile_ids"].append(profile_id)
                if bundle_id not in entry["bundle_ids"]:
                    entry["bundle_ids"].append(bundle_id)
                if concern not in entry["concerns"]:
                    entry["concerns"].append(concern)
                entry["freshness_hours"] = min(int(entry["freshness_hours"]), freshness_hours)

    seed_images = [
        {
            "ref": ref,
            "image_ids": sorted(entry["image_ids"]),
            "profile_ids": sorted(entry["profile_ids"]),
            "bundle_ids": sorted(entry["bundle_ids"]),
            "concerns": sorted(entry["concerns"]),
            "freshness_hours": int(entry["freshness_hours"]),
        }
        for ref, entry in sorted(entries_by_ref.items())
    ]
    return {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "generated_at": isoformat(utc_now()),
        "profile_count": len(profiles_summary),
        "profiles": sorted(profiles_summary, key=lambda item: item["id"]),
        "seed_images": seed_images,
    }


def plan_from_file(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    return require_mapping(payload, str(path))


def pull_image(ref: str) -> tuple[subprocess.CompletedProcess[str], bool]:
    completed = subprocess.run(
        ["docker", "pull", ref],
        text=True,
        capture_output=True,
        check=False,
    )
    combined_output = "\n".join(
        line.strip() for line in (completed.stdout + "\n" + completed.stderr).splitlines() if line.strip()
    )
    changed = any(
        marker in combined_output
        for marker in (
            "Downloaded newer image",
            "Pull complete",
            "Status: Downloaded newer image",
        )
    )
    return completed, changed


def warm_plan(plan: dict[str, Any], *, plan_file: Path, receipt_file: Path, required: bool) -> dict[str, Any]:
    seed_images = require_list(plan.get("seed_images"), f"{plan_file}.seed_images")
    if required and not seed_images:
        raise ValueError(f"{plan_file} does not contain any seed_images entries")

    receipt_results: list[dict[str, Any]] = []
    changed_refs: list[str] = []
    failed_refs: list[str] = []

    for raw_image in seed_images:
        image = require_mapping(raw_image, f"{plan_file}.seed_images[]")
        ref = require_str(image.get("ref"), f"{plan_file}.seed_images[].ref")
        completed, changed = pull_image(ref)
        combined_output = "\n".join(
            line.strip() for line in (completed.stdout + "\n" + completed.stderr).splitlines() if line.strip()
        )
        detail = combined_output.splitlines()[-1] if combined_output else "docker pull returned no output"
        status = "pass" if completed.returncode == 0 else "fail"
        if changed:
            changed_refs.append(ref)
        if completed.returncode != 0:
            failed_refs.append(ref)
        receipt_results.append(
            {
                "ref": ref,
                "status": status,
                "changed": changed,
                "detail": detail,
                "profile_ids": list(image.get("profile_ids", [])),
                "bundle_ids": list(image.get("bundle_ids", [])),
                "concerns": list(image.get("concerns", [])),
                "freshness_hours": image.get("freshness_hours"),
            }
        )

    receipt = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "plan_generated_at": plan.get("generated_at"),
        "warmed_at": isoformat(utc_now()),
        "result": "fail" if failed_refs else "pass",
        "image_count": len(seed_images),
        "changed_count": len(changed_refs),
        "successful_pulls": len(seed_images) - len(failed_refs),
        "failed_pulls": len(failed_refs),
        "changed_refs": sorted(changed_refs),
        "failed_refs": sorted(failed_refs),
        "results": receipt_results,
    }
    write_json(receipt_file, receipt)
    return receipt


def verify_receipt(
    *,
    plan: dict[str, Any],
    receipt: dict[str, Any],
    required: bool,
    max_age_seconds: int | None,
) -> None:
    seed_images = require_list(plan.get("seed_images"), "plan.seed_images")
    if required and not seed_images:
        raise ValueError("plan.seed_images must not be empty when --required is set")

    if receipt.get("result") != "pass":
        raise ValueError("warm receipt result must be 'pass'")

    image_count = require_int(receipt.get("image_count"), "receipt.image_count", minimum=0)
    successful_pulls = require_int(receipt.get("successful_pulls"), "receipt.successful_pulls", minimum=0)
    failed_pulls = require_int(receipt.get("failed_pulls"), "receipt.failed_pulls", minimum=0)
    if image_count != len(seed_images):
        raise ValueError("warm receipt image_count does not match the current seed plan")
    if successful_pulls != len(seed_images) or failed_pulls != 0:
        raise ValueError("warm receipt must report all seed images as successfully pulled")

    warmed_at = parse_timestamp(require_str(receipt.get("warmed_at"), "receipt.warmed_at"))
    if max_age_seconds is not None:
        age_seconds = int((utc_now() - warmed_at).total_seconds())
        if age_seconds > max_age_seconds:
            raise ValueError(f"warm receipt is stale: age {age_seconds}s exceeds allowed max-age {max_age_seconds}s")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan, warm, and verify governed repo-deploy base image caches.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate the repo-deploy base-image profile catalog.")
    validate_parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)

    plan_parser = subparsers.add_parser(
        "plan", help="Render a warm plan from the repo-deploy base-image profile catalog."
    )
    plan_parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)

    warm_parser = subparsers.add_parser("warm", help="Warm the images declared in a rendered plan and write a receipt.")
    warm_parser.add_argument("--plan-file", type=Path, required=True)
    warm_parser.add_argument("--receipt-file", type=Path, required=True)
    warm_parser.add_argument("--required", action="store_true", help="Fail when the plan contains no images.")

    verify_parser = subparsers.add_parser("verify", help="Verify a warm receipt against the current plan.")
    verify_parser.add_argument("--plan-file", type=Path, required=True)
    verify_parser.add_argument("--receipt-file", type=Path, required=True)
    verify_parser.add_argument("--required", action="store_true", help="Fail when the plan contains no images.")
    verify_parser.add_argument("--max-age-seconds", type=int, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            catalog = load_profile_catalog(args.catalog)
            validate_profile_catalog(catalog, path=args.catalog)
            print("Repo-deploy base image profile catalog OK")
            return 0

        if args.command == "plan":
            catalog = load_profile_catalog(args.catalog)
            plan = build_plan(catalog)
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0

        if args.command == "warm":
            plan = plan_from_file(args.plan_file)
            receipt = warm_plan(plan, plan_file=args.plan_file, receipt_file=args.receipt_file, required=args.required)
            print(json.dumps(receipt, indent=2, sort_keys=True))
            return 0 if receipt["result"] == "pass" else 1

        if args.command == "verify":
            plan = plan_from_file(args.plan_file)
            receipt = require_mapping(load_json(args.receipt_file), str(args.receipt_file))
            verify_receipt(
                plan=plan,
                receipt=receipt,
                required=args.required,
                max_age_seconds=args.max_age_seconds,
            )
            print(json.dumps(receipt, indent=2, sort_keys=True))
            return 0
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"repo-deploy-image-cache: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
