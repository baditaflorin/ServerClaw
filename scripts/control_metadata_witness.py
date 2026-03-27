#!/usr/bin/env python3
"""Build and verify off-host witness bundles for control metadata."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE_ROOT = DEFAULT_REPO_ROOT / ".local" / "control-metadata-witness" / "archive"
DEFAULT_STAGING_ROOT = DEFAULT_REPO_ROOT / ".local" / "control-metadata-witness" / "staging"
DEFAULT_RECEIPT_DIR = DEFAULT_REPO_ROOT / "receipts" / "witness-replication"
UTC = dt.timezone.utc

REQUIRED_SNAPSHOT_FILES = (
    "VERSION",
    "README.md",
    "changelog.md",
    "workstreams.yaml",
    "config/controller-local-secrets.json",
    "config/disaster-recovery-targets.json",
    "docs/runbooks/disaster-recovery.md",
    "inventory/hosts.yml",
    "inventory/group_vars/all.yml",
    "inventory/host_vars/proxmox_florin.yml",
    "versions/stack.yaml",
)
REQUIRED_SNAPSHOT_PREFIXES = (
    "docs/adr/",
    "docs/runbooks/",
    "docs/workstreams/",
    "receipts/",
    "versions/",
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def utc_now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def require_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = run_command(command, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "command failed")
    return result


def git_output(repo_root: Path, *args: str) -> str:
    return require_command(["git", "-C", str(repo_root), *args]).stdout.strip()


def canonical_repo_root(repo_root: Path) -> Path:
    resolved_root = repo_root.resolve()
    return Path(git_output(resolved_root, "rev-parse", "--show-toplevel"))


def git_current_branch(repo_root: Path) -> str:
    branch = run_command(["git", "-C", str(repo_root), "symbolic-ref", "--quiet", "--short", "HEAD"])
    if branch.returncode != 0:
        raise RuntimeError("control metadata witness requires a branch checkout or an explicit --git-remote-ref")
    return branch.stdout.strip()


def resolve_remote_ref(repo_root: Path, remote: str, remote_ref: str | None) -> str:
    if remote_ref:
        return remote_ref
    current_branch = git_current_branch(repo_root)
    upstream = run_command(
        ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
    )
    if upstream.returncode == 0:
        upstream_ref = upstream.stdout.strip()
        if upstream_ref.startswith(f"{remote}/"):
            upstream_branch = upstream_ref.split("/", 1)[1]
            if upstream_branch == current_branch:
                return f"refs/heads/{upstream_branch}"
    return f"refs/heads/{current_branch}"


def verify_remote_head(repo_root: Path, remote: str, remote_ref: str) -> dict[str, str]:
    head_commit = git_output(repo_root, "rev-parse", "HEAD")
    remote_result = require_command(["git", "-C", str(repo_root), "ls-remote", "--exit-code", remote, remote_ref])
    remote_commit = remote_result.stdout.split()[0]
    if remote_commit != head_commit:
        raise RuntimeError(
            f"remote target {remote} {remote_ref} points to {remote_commit}, expected current HEAD {head_commit}"
        )
    remote_url = git_output(repo_root, "remote", "get-url", remote)
    return {
        "remote": remote,
        "remote_ref": remote_ref,
        "remote_url": remote_url,
        "commit": remote_commit,
        "status": "pass",
    }


def build_snapshot_archive(repo_root: Path, target_path: Path) -> None:
    require_command(
        [
            "git",
            "-C",
            str(repo_root),
            "archive",
            "--format=tar",
            "--output",
            str(target_path),
            "HEAD",
        ]
    )


def list_snapshot_entries(snapshot_path: Path) -> list[str]:
    with tarfile.open(snapshot_path, "r") as archive:
        return sorted(member.name for member in archive.getmembers() if member.name and member.name != ".")


def assert_snapshot_contract(entries: list[str]) -> None:
    entry_set = set(entries)
    missing_files = [path for path in REQUIRED_SNAPSHOT_FILES if path not in entry_set]
    missing_prefixes = [prefix for prefix in REQUIRED_SNAPSHOT_PREFIXES if not any(name.startswith(prefix) for name in entries)]
    problems = [f"missing file {path}" for path in missing_files] + [f"missing tree {prefix}" for prefix in missing_prefixes]
    if problems:
        raise RuntimeError("snapshot contract failed: " + ", ".join(problems))


def verify_bundle_clone(bundle_path: Path, required_files: tuple[str, ...] = REQUIRED_SNAPSHOT_FILES) -> None:
    with tempfile.TemporaryDirectory(prefix="witness-clone-") as temp_dir:
        clone_dir = Path(temp_dir) / "clone"
        require_command(["git", "clone", str(bundle_path), str(clone_dir)])
        missing = [path for path in required_files if not (clone_dir / path).exists()]
        if missing:
            raise RuntimeError("cloned witness bundle is missing " + ", ".join(missing))


def build_witness_manifest(
    *,
    repo_root: Path,
    bundle_id: str,
    head_commit: str,
    branch: str,
    repo_version: str,
    remote_status: dict[str, str],
    stage_dir: Path,
    snapshot_entries: list[str],
) -> dict[str, Any]:
    files = []
    for name in ("repo.bundle", "repo-snapshot.tar"):
        path = stage_dir / name
        files.append(
            {
                "name": name,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": "1.0.0",
        "bundle_id": bundle_id,
        "recorded_at": utc_now_iso(),
        "repo_root": str(repo_root),
        "repo_version": repo_version,
        "head_commit": head_commit,
        "branch": branch,
        "remote_verification": remote_status,
        "files": files,
        "required_snapshot_files": list(REQUIRED_SNAPSHOT_FILES),
        "required_snapshot_prefixes": list(REQUIRED_SNAPSHOT_PREFIXES),
        "snapshot_entry_count": len(snapshot_entries),
        "bootstrap_paths": [
            "docs/runbooks/disaster-recovery.md",
            "docs/runbooks/configure-control-plane-recovery.md",
            "config/controller-local-secrets.json",
            "config/disaster-recovery-targets.json",
            "versions/stack.yaml",
            "workstreams.yaml",
        ],
        "notes": [
            "repo.bundle is the recoverable git witness",
            "repo-snapshot.tar is the immutable tree snapshot for direct inspection without git history",
            "config/controller-local-secrets.json exposes secret locator metadata only, not secret values",
        ],
    }


def build_local_witness_bundle(
    repo_root: Path,
    *,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    git_remote: str = "origin",
    git_remote_ref: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    repo_root = canonical_repo_root(repo_root)
    staging_root.mkdir(parents=True, exist_ok=True)

    head_commit = git_output(repo_root, "rev-parse", "HEAD")
    branch = git_current_branch(repo_root)
    repo_version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    bundle_id = f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{head_commit[:12]}"
    stage_dir = staging_root / bundle_id
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    remote_ref = resolve_remote_ref(repo_root, git_remote, git_remote_ref)
    remote_status = verify_remote_head(repo_root, git_remote, remote_ref)

    bundle_path = stage_dir / "repo.bundle"
    snapshot_path = stage_dir / "repo-snapshot.tar"
    require_command(["git", "-C", str(repo_root), "bundle", "create", str(bundle_path), "--all"])
    build_snapshot_archive(repo_root, snapshot_path)

    snapshot_entries = list_snapshot_entries(snapshot_path)
    assert_snapshot_contract(snapshot_entries)
    verify_bundle_clone(bundle_path)

    manifest = build_witness_manifest(
        repo_root=repo_root,
        bundle_id=bundle_id,
        head_commit=head_commit,
        branch=branch,
        repo_version=repo_version,
        remote_status=remote_status,
        stage_dir=stage_dir,
        snapshot_entries=snapshot_entries,
    )
    write_json(stage_dir / "witness-manifest.json", manifest)
    return stage_dir, manifest


def verify_generation(generation_dir: Path) -> dict[str, Any]:
    manifest_path = generation_dir / "witness-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"missing witness manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for file_entry in manifest.get("files", []):
        target = generation_dir / file_entry["name"]
        if not target.is_file():
            raise RuntimeError(f"missing witness artifact: {target}")
        observed_sha = sha256_file(target)
        if observed_sha != file_entry["sha256"]:
            raise RuntimeError(f"checksum mismatch for {target.name}: {observed_sha} != {file_entry['sha256']}")
    verify_bundle_clone(generation_dir / "repo.bundle")
    entries = list_snapshot_entries(generation_dir / "repo-snapshot.tar")
    assert_snapshot_contract(entries)
    return manifest


def promote_generation(staging_dir: Path, archive_root: Path, bundle_id: str) -> Path:
    archive_root.mkdir(parents=True, exist_ok=True)
    staging_root = archive_root / ".staging"
    generations_root = archive_root / "generations"
    staging_root.mkdir(parents=True, exist_ok=True)
    generations_root.mkdir(parents=True, exist_ok=True)

    generation_staging_dir = staging_root / bundle_id
    generation_dir = generations_root / bundle_id
    latest_link = archive_root / "latest"

    if generation_staging_dir.exists():
        shutil.rmtree(generation_staging_dir)
    if generation_dir.exists():
        raise RuntimeError(f"witness generation already exists: {generation_dir}")

    try:
        shutil.copytree(staging_dir, generation_staging_dir)
        verify_generation(generation_staging_dir)
        generation_staging_dir.rename(generation_dir)

        replacement_link = archive_root / ".latest.tmp"
        if replacement_link.exists() or replacement_link.is_symlink():
            replacement_link.unlink()
        os.symlink(str(generation_dir), str(replacement_link))
        replacement_link.replace(latest_link)
    except Exception:
        if generation_staging_dir.exists():
            shutil.rmtree(generation_staging_dir, ignore_errors=True)
        raise

    return generation_dir


def build_receipt(manifest: dict[str, Any], generation_dir: Path) -> dict[str, Any]:
    receipt_id = f"{manifest['bundle_id']}-control-metadata-witness"
    return {
        "schema_version": "1.0.0",
        "receipt_id": receipt_id,
        "recorded_at": utc_now_iso(),
        "bundle_id": manifest["bundle_id"],
        "repo_version": manifest["repo_version"],
        "head_commit": manifest["head_commit"],
        "branch": manifest["branch"],
        "targets": {
            "git_remote": manifest["remote_verification"],
            "archive": {
                "status": "pass",
                "generation_dir": str(generation_dir),
                "latest_pointer": str(generation_dir.parent.parent / "latest"),
            },
        },
        "verification": {
            "bundle_clone": "pass",
            "snapshot_contract": "pass",
        },
    }


def sync_control_metadata_witness(
    repo_root: Path,
    *,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    receipt_dir: Path = DEFAULT_RECEIPT_DIR,
    git_remote: str = "origin",
    git_remote_ref: str | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    stage_dir, manifest = build_local_witness_bundle(
        repo_root,
        staging_root=staging_root,
        git_remote=git_remote,
        git_remote_ref=git_remote_ref,
    )
    generation_dir = promote_generation(stage_dir, archive_root, manifest["bundle_id"])
    verify_generation(generation_dir)
    receipt = build_receipt(manifest, generation_dir)
    receipt_path = receipt_dir / f"{receipt['receipt_id']}.json"
    write_json(receipt_path, receipt)
    return generation_dir, receipt_path, receipt


def resolve_generation_dir(archive_root: Path, generation: str) -> Path:
    if generation == "latest":
        latest = archive_root / "latest"
        if not latest.exists():
            raise RuntimeError(f"witness latest pointer is missing under {archive_root}")
        return latest.resolve()
    return archive_root / "generations" / generation


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and verify control metadata witness bundles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Build a witness bundle and replicate it to the archive target.")
    sync_parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    sync_parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    sync_parser.add_argument("--staging-root", type=Path, default=DEFAULT_STAGING_ROOT)
    sync_parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    sync_parser.add_argument("--git-remote", default="origin")
    sync_parser.add_argument("--git-remote-ref")

    verify_parser = subparsers.add_parser("verify", help="Verify an archived witness generation.")
    verify_parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    verify_parser.add_argument("--generation", default="latest")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "sync":
        generation_dir, receipt_path, receipt = sync_control_metadata_witness(
            args.repo_root,
            archive_root=args.archive_root,
            staging_root=args.staging_root,
            receipt_dir=args.receipt_dir,
            git_remote=args.git_remote,
            git_remote_ref=args.git_remote_ref,
        )
        print(
            json.dumps(
                {
                    "generation_dir": str(generation_dir),
                    "receipt_path": str(receipt_path),
                    "bundle_id": receipt["bundle_id"],
                },
                indent=2,
            )
        )
        return 0

    generation_dir = resolve_generation_dir(args.archive_root, args.generation)
    manifest = verify_generation(generation_dir)
    print(json.dumps({"generation_dir": str(generation_dir), "bundle_id": manifest["bundle_id"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
