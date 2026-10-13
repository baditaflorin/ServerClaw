#!/usr/bin/env python3
"""Build and scan the explicitly pinned patched runtime images on the remote builder."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from container_image_policy import validate_image_catalog
from controller_automation_toolkit import emit_cli_error, write_json
from sbom_scanner import (
    CVE_RECEIPTS_DIR,
    DEFAULT_GRYPE_DB_CACHE_DIR,
    SBOM_RECEIPTS_DIR,
    ensure_grype_database,
    load_scanner_config,
    now_utc,
    relpath,
    scan_catalog_image,
)
from outline_client import publish_receipt_to_outline
from upgrade_container_image import build_scan_receipt


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "build" / "patched-images" / "manifest.json"
IMAGE_IDS = ("outline", "glitchtip", "minio", "valkey")
BUILD_IMAGE_IDS = ("outline", "glitchtip", "minio")
REGISTRY_PATTERN = re.compile(r"^[a-zA-Z0-9.-]+(?::[0-9]+)?$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--image", choices=(*IMAGE_IDS, "all"), default="all")
    result.add_argument("--registry", required=True, help="Harbor hostname only, with no scheme or path.")
    result.add_argument(
        "--publisher-secret-file",
        type=Path,
        help="Override the ignored controller-local Harbor publisher credential file.",
    )
    result.add_argument("--write-receipts", action="store_true", help="Write candidate SBOM/CVE receipts into Git.")
    result.add_argument(
        "--update-catalog",
        action="store_true",
        help="Pin all selected images only if every exact pushed digest passes the zero-Critical gate.",
    )
    return result


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0.0" or manifest.get("platform") != "linux/amd64":
        raise ValueError("patched-image manifest has an unsupported schema or platform")
    images = manifest.get("images")
    if not isinstance(images, dict) or set(images) != set(IMAGE_IDS):
        raise ValueError("patched-image manifest must define exactly Outline, GlitchTip, MinIO, and Valkey")
    for image_id, entry in images.items():
        catalog_ids = entry.get("catalog_ids")
        if (
            not isinstance(catalog_ids, list)
            or not catalog_ids
            or not all(isinstance(value, str) for value in catalog_ids)
        ):
            raise ValueError(f"{image_id} must declare one or more catalog_ids")
        if entry.get("kind") == "build":
            if not re.fullmatch(r"[0-9a-f]{40}", str(entry.get("source_commit", ""))):
                raise ValueError(f"{image_id} source_commit must be a full 40-character Git commit")
            for key in ("source_repository", "source_ref", "tag_prefix", "repositories"):
                if not entry.get(key):
                    raise ValueError(f"{image_id} manifest is missing {key}")
            for key in ("patch", "dockerfile"):
                relative = entry.get(key)
                if relative and not (REPO_ROOT / relative).is_file():
                    raise ValueError(f"{image_id} manifest references missing {key}: {relative}")
        elif entry.get("kind") == "external":
            for key in ("registry_ref", "tag", "digest", "platform"):
                if not entry.get(key):
                    raise ValueError(f"{image_id} manifest is missing {key}")
            if not DIGEST_PATTERN.fullmatch(str(entry["digest"])):
                raise ValueError(f"{image_id} digest must be sha256-pinned")
            if entry["platform"] != "linux/amd64":
                raise ValueError(f"{image_id} platform must be linux/amd64")
        else:
            raise ValueError(f"{image_id} has unsupported kind {entry.get('kind')!r}")
    return manifest


def common_repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=REPO_ROOT, text=True, capture_output=True, check=True
    )
    common_dir = Path(result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = (REPO_ROOT / common_dir).resolve()
    return common_dir.parent


def publisher_secret_path(override: Path | None = None) -> Path:
    if override:
        return override.expanduser().resolve()
    return common_repo_root() / ".local" / "harbor" / "patched-runtime-publisher.json"


def read_publisher_secret(path: Path, *, project: str) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("Harbor publisher credential is missing; converge the managed Harbor role first")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Harbor publisher credential must be owner-readable only (mode 0600)")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("project") != project:
        raise ValueError("Harbor publisher credential is scoped to the wrong project")
    username = payload.get("username")
    secret = payload.get("secret")
    if not isinstance(username, str) or not username or not isinstance(secret, str) or not secret:
        raise ValueError("Harbor publisher credential file is incomplete")
    return {"username": username, "secret": secret}


def image_tag(entry: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps(entry, sort_keys=True, separators=(",", ":")).encode())
    for key in ("patch", "dockerfile"):
        relative = entry.get(key)
        if relative:
            digest.update((REPO_ROOT / relative).read_bytes())
    return f"{entry['tag_prefix']}-{digest.hexdigest()[:8]}"


def remote_build_command(
    *,
    image_id: str,
    registry: str,
    project: str,
    username: str,
    tag: str,
    entry: dict[str, Any],
) -> str:
    arguments = [
        "bash",
        "build/patched-images/build_remote.sh",
        image_id,
        registry,
        project,
        username,
        tag,
        entry["source_ref"],
        entry["source_commit"],
        entry["source_repository"],
        entry.get("patch", ""),
        entry.get("dockerfile", ""),
    ]
    return " ".join(shlex.quote(item) for item in arguments)


def build_remote(image_id: str, command: str, secret: str) -> str:
    # Make disconnects recipe stdin, which would make `docker login
    # --password-stdin` receive an empty value on the remote builder. Invoke
    # the same strict configured remote-execution path directly so the secret
    # stays on stdin and never enters argv or the environment.
    remote_exec = REPO_ROOT / "scripts" / "remote_exec.sh"
    env = os.environ.copy()
    env["SERVICE"] = "patched-runtime"
    env["COMMAND"] = command
    with tempfile.TemporaryDirectory(prefix="patched-image-registry-secret-") as secret_dir:
        secret_path = Path(secret_dir) / "stdin"
        secret_path.write_text(secret + "\n", encoding="utf-8")
        secret_path.chmod(0o600)
        env["REMOTE_EXEC_STDIN_FILE"] = str(secret_path)
        result = subprocess.run(
            [str(remote_exec), "remote-image-build"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=5400,
        )
    combined = (result.stdout + result.stderr).replace(secret, "[REDACTED]")
    if result.returncode != 0:
        raise RuntimeError(f"remote {image_id} build failed (exit {result.returncode}):\n{combined[-5000:]}")
    match = re.search(
        r"PATCHED_IMAGE_RESULT\s+image=" + re.escape(image_id) + r"\s+digest=(sha256:[0-9a-f]{64})", combined
    )
    if not match:
        raise RuntimeError(f"remote {image_id} build did not return a valid digest:\n{combined[-3000:]}")
    print(combined, end="" if combined.endswith("\n") else "\n")
    return match.group(1)


def scan_candidate(
    *,
    image_id: str,
    image_ref: str,
    registry_auth: dict[str, str] | None,
    write_receipts: bool,
    scanned_at: datetime,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="patched-image-registry-auth-") as config_dir:
        os.chmod(config_dir, 0o700)
        if registry_auth:
            login = subprocess.run(
                [
                    "docker",
                    "--config",
                    config_dir,
                    "login",
                    "--username",
                    registry_auth["username"],
                    "--password-stdin",
                    registry_auth["registry"],
                ],
                input=registry_auth["secret"] + "\n",
                text=True,
                capture_output=True,
                check=False,
            )
            if login.returncode != 0:
                raise RuntimeError("temporary Harbor publisher login for scanning failed")
        prior_docker_config = os.environ.get("DOCKER_CONFIG")
        os.environ["DOCKER_CONFIG"] = config_dir
        try:
            if write_receipts:
                sbom_dir, cve_dir = SBOM_RECEIPTS_DIR, CVE_RECEIPTS_DIR
            else:
                candidate_root = REPO_ROOT / ".local" / "image-upgrade-scans" / "patched-images" / image_id
                sbom_dir, cve_dir = candidate_root / "sbom", candidate_root / "cve"
            scanner_config = load_scanner_config()
            sbom_path, cve_path, cve_receipt = scan_catalog_image(
                image_id=image_id,
                image_ref=image_ref,
                runtime_host="image-build",
                platform_name="linux/amd64",
                sbom_dir=sbom_dir,
                cve_dir=cve_dir,
                config=scanner_config,
                scanned_at=scanned_at,
                update_grype_db=False,
                use_artifact_cache=False,
            )
        finally:
            if prior_docker_config is None:
                os.environ.pop("DOCKER_CONFIG", None)
            else:
                os.environ["DOCKER_CONFIG"] = prior_docker_config
            if registry_auth:
                subprocess.run(
                    ["docker", "--config", config_dir, "logout", registry_auth["registry"]],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=30,
                )

    receipt = build_scan_receipt(
        image_id=image_id,
        image_ref=image_ref,
        scanned_on=scanned_at.date().isoformat(),
        scanner_config=scanner_config,
        sbom_path=sbom_path,
        cve_path=cve_path,
        cve_receipt=cve_receipt,
    )
    if write_receipts:
        digest_short = image_ref.rsplit("@", 1)[1].removeprefix("sha256:")[:12]
        summary_path = (
            REPO_ROOT
            / "receipts"
            / "image-scans"
            / (f"{scanned_at.date().isoformat()}-patched-{image_id.replace('_', '-')}-{digest_short}.json")
        )
        write_json(summary_path, receipt)
        publish_receipt_to_outline(summary_path)
        receipt["scan_receipt"] = relpath(summary_path)
    return receipt


def update_catalog_entries(catalog: dict[str, Any], results: list[dict[str, Any]], *, pinned_on: str) -> dict[str, Any]:
    updated = json.loads(json.dumps(catalog))
    for result in results:
        image_id = result["catalog_id"]
        entry = updated["images"][image_id]
        entry["registry_ref"] = result["registry_ref"]
        entry["tag"] = result["tag"]
        entry["digest"] = result["digest"]
        entry["ref"] = result["image_ref"]
        entry["pinned_on"] = pinned_on
        entry["scan_receipt"] = result["scan_receipt"]
        entry["scan_status"] = "pass_no_critical"
        entry.pop("exception", None)
    validate_image_catalog(updated)
    return updated


def main() -> int:
    args = parser().parse_args()
    try:
        if not REGISTRY_PATTERN.fullmatch(args.registry):
            raise ValueError("--registry must be a hostname with no scheme or repository path")
        write_receipts = args.write_receipts or args.update_catalog
        manifest = load_manifest()
        project = str(manifest["registry_project"])
        secret_path = publisher_secret_path(args.publisher_secret_file)
        selected = IMAGE_IDS if args.image == "all" else (args.image,)
        build_selected = [image_id for image_id in selected if manifest["images"][image_id]["kind"] == "build"]
        credential = read_publisher_secret(secret_path, project=project) if build_selected else None
        ensure_grype_database(load_scanner_config(), grype_db_cache_dir=DEFAULT_GRYPE_DB_CACHE_DIR)
        scan_time = now_utc()
        results: list[dict[str, Any]] = []
        for image_id in selected:
            entry = manifest["images"][image_id]
            registry_auth = None
            if entry["kind"] == "build":
                assert credential is not None
                tag = image_tag(entry)
                command = remote_build_command(
                    image_id=image_id,
                    registry=args.registry,
                    project=project,
                    username=credential["username"],
                    tag=tag,
                    entry=entry,
                )
                digest = build_remote(image_id, command, credential["secret"])
                if not DIGEST_PATTERN.fullmatch(digest):
                    raise ValueError(f"remote builder returned an invalid {image_id} digest")
                registry_ref = f"{args.registry}/{project}/{entry['repositories'][-1]}"
                image_ref = f"{registry_ref}:{tag}@{digest}"
                registry_auth = {"registry": args.registry, **credential}
            else:
                registry_ref = str(entry["registry_ref"])
                tag = str(entry["tag"])
                digest = str(entry["digest"])
                image_ref = f"{registry_ref}:{tag}@{digest}"

            for catalog_id in entry["catalog_ids"]:
                scan = scan_candidate(
                    image_id=catalog_id,
                    image_ref=image_ref,
                    registry_auth=registry_auth,
                    write_receipts=write_receipts,
                    scanned_at=scan_time,
                )
                summary = scan["summary"]
                results.append(
                    {
                        "candidate_id": image_id,
                        "catalog_id": catalog_id,
                        "registry_ref": registry_ref,
                        "tag": tag,
                        "digest": digest,
                        "image_ref": image_ref,
                        "scan_receipt": scan.get("scan_receipt", ""),
                        "summary": summary,
                        "eligible": summary["critical"] == 0 and summary["blocking_findings_with_fix"] == 0,
                    }
                )

        passed = all(result["eligible"] for result in results)
        if args.update_catalog and not passed:
            raise ValueError(
                "at least one candidate still has Critical or fixable High/Critical findings; catalog was not changed"
            )
        if args.update_catalog:
            catalog_path = REPO_ROOT / "config" / "image-catalog.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            updated = update_catalog_entries(
                catalog,
                results,
                pinned_on=scan_time.date().isoformat(),
            )
            write_json(catalog_path, updated)
        print(
            json.dumps(
                {"results": results, "all_candidates_pass": passed, "catalog_updated": args.update_catalog}, indent=2
            )
        )
        return 0 if passed else 2
    except (OSError, json.JSONDecodeError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Build patched runtime images", exc)


if __name__ == "__main__":
    sys.exit(main())
