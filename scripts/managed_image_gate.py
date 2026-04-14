#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, repo_path
from sbom_scanner import (
    DEFAULT_GRYPE_DB_CACHE_DIR,
    DEFAULT_SYFT_CACHE_DIR,
    load_scanner_config,
    relpath,
    scan_catalog_image,
)


REPO_ROOT = repo_path()
IMAGE_CATALOG_PATH = repo_path("config", "image-catalog.json")


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result.stdout


def load_catalog_from_git(revision: str, path: Path) -> dict[str, Any]:
    payload = git_output("show", f"{revision}:{relpath(path)}")
    return json.loads(payload)


def changed_image_ids(baseline_revision: str, catalog_path: Path) -> list[str]:
    baseline = load_catalog_from_git(baseline_revision, catalog_path)
    current = json.loads(catalog_path.read_text(encoding="utf-8"))
    baseline_images = baseline.get("images", {})
    current_images = current.get("images", {})
    if not isinstance(baseline_images, dict) or not isinstance(current_images, dict):
        raise ValueError("config/image-catalog.json must define an images object")
    changed: list[str] = []
    for image_id, entry in sorted(current_images.items()):
        if not isinstance(entry, dict):
            continue
        baseline_entry = baseline_images.get(image_id)
        if not isinstance(baseline_entry, dict):
            changed.append(image_id)
            continue
        if entry.get("ref") != baseline_entry.get("ref"):
            changed.append(image_id)
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the ADR 0298 managed-image gate on any image refs changed from the baseline revision."
    )
    parser.add_argument("--baseline-revision", default="origin/main")
    parser.add_argument("--image-catalog", type=Path, default=IMAGE_CATALOG_PATH)
    parser.add_argument("--working-root", type=Path, default=repo_path(".local", "managed-image-gate"))
    parser.add_argument("--skip-artifact-cache", action="store_true")
    parser.add_argument("--skip-db-update", action="store_true")
    parser.add_argument("--syft-cache-dir", type=Path, default=DEFAULT_SYFT_CACHE_DIR)
    parser.add_argument("--grype-db-cache-dir", type=Path, default=DEFAULT_GRYPE_DB_CACHE_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        changed = changed_image_ids(args.baseline_revision, args.image_catalog)
        if not changed:
            print("No managed image refs changed from the baseline revision.")
            return 0
        config = load_scanner_config()
        catalog = json.loads(args.image_catalog.read_text(encoding="utf-8"))
        sbom_dir = args.working_root / "sbom"
        cve_dir = args.working_root / "cve"
        blocking_images: list[dict[str, Any]] = []
        scanned_images: list[dict[str, Any]] = []
        for index, image_id in enumerate(changed):
            entry = catalog["images"][image_id]
            _sbom_path, cve_path, receipt = scan_catalog_image(
                image_id=image_id,
                image_ref=str(entry["ref"]),
                runtime_host=entry.get("runtime_host"),
                platform_name=str(entry.get("platform", "linux/amd64")),
                sbom_dir=sbom_dir,
                cve_dir=cve_dir,
                config=config,
                syft_cache_dir=args.syft_cache_dir,
                grype_db_cache_dir=args.grype_db_cache_dir,
                update_grype_db=not args.skip_db_update and index == 0,
                use_artifact_cache=not args.skip_artifact_cache,
            )
            scanned_images.append(
                {
                    "image_id": image_id,
                    "image_ref": entry["ref"],
                    "cve_receipt": relpath(cve_path),
                    "summary": receipt["summary"],
                }
            )
            if receipt["summary"]["blocking_findings_with_fix"] > 0:
                blocking_images.append(scanned_images[-1])
        print(json.dumps({"changed_images": scanned_images, "blocking_images": blocking_images}, indent=2))
        return 2 if blocking_images else 0
    except Exception as exc:
        return emit_cli_error("Managed image gate", exc)


if __name__ == "__main__":
    sys.exit(main())
