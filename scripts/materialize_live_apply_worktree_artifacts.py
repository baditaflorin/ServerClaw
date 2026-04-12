#!/usr/bin/env python3
"""Materialize generated repo surfaces required by fresh-worktree live-apply wrappers."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2, copytree


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ArtifactSpec:
    kind: str
    relative_path: str
    description: str


ARTIFACTS: dict[str, ArtifactSpec] = {
    "platform_vars": ArtifactSpec(
        kind="file",
        relative_path="inventory/group_vars/platform.yml",
        description="Generated platform facts library plus ADR 0374 derived inputs.",
    ),
    "gate_bypass_keep": ArtifactSpec(
        kind="file",
        relative_path="receipts/gate-bypasses/.gitkeep",
        description="Non-empty gate-bypass sentinel for fresh worktrees.",
    ),
    "drift_reports_dir": ArtifactSpec(
        kind="directory",
        relative_path="receipts/drift-reports",
        description="Controller-local drift report directory consumed by generated portals.",
    ),
    "https_tls_targets": ArtifactSpec(
        kind="file",
        relative_path="config/prometheus/file_sd/https_tls_targets.yml",
        description="Generated HTTPS/TLS target catalog consumed by canonical-truth checks.",
    ),
    "https_tls_alerts": ArtifactSpec(
        kind="file",
        relative_path="config/prometheus/rules/https_tls_alerts.yml",
        description="Generated HTTPS/TLS alert rules kept alongside the target catalog.",
    ),
    "uptime_kuma_monitors": ArtifactSpec(
        kind="file",
        relative_path="config/uptime-kuma/monitors.json",
        description="Generated Uptime Kuma monitor catalog consumed by the changelog portal.",
    ),
    "image_scan_receipts": ArtifactSpec(
        kind="directory",
        relative_path="receipts/image-scans",
        description="Latest container image scan receipts required by vulnerability budget gates.",
    ),
}


def artifact_path(artifact_id: str, *, repo_root: Path = REPO_ROOT) -> Path:
    spec = ARTIFACTS[artifact_id]
    return repo_root / spec.relative_path


def artifact_ready(artifact_id: str, *, repo_root: Path = REPO_ROOT) -> bool:
    path = artifact_path(artifact_id, repo_root=repo_root)
    spec = ARTIFACTS[artifact_id]
    if spec.kind == "directory":
        return path.is_dir()
    return path.is_file() and path.stat().st_size > 0


def run_command(argv: list[str], *, repo_root: Path = REPO_ROOT) -> None:
    completed = subprocess.run(
        argv,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise RuntimeError(f"{' '.join(argv)} exited {completed.returncode}: {detail.splitlines()[-1]}")


def find_primary_worktree(repo_root: Path) -> Path:
    if repo_root.parent.name == ".worktrees":
        shared_root = repo_root.parent.parent
        if shared_root != repo_root and shared_root.exists():
            return shared_root

    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return repo_root

    current_worktree: dict[str, str] = {}
    candidates: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            if current_worktree:
                candidates.append(current_worktree)
                current_worktree = {}
            continue
        key, _, value = line.partition(" ")
        current_worktree[key] = value.strip()
    if current_worktree:
        candidates.append(current_worktree)

    for entry in candidates:
        if entry.get("branch") == "refs/heads/main":
            return Path(entry["worktree"])
    return repo_root


def materialize_artifact(artifact_id: str, *, repo_root: Path = REPO_ROOT) -> Path:
    path = artifact_path(artifact_id, repo_root=repo_root)

    if artifact_id == "platform_vars":
        run_command(["make", "generate-platform-vars"], repo_root=repo_root)
    elif artifact_id in {"https_tls_targets", "https_tls_alerts"}:
        run_command(["make", "generate-https-tls-assurance"], repo_root=repo_root)
    elif artifact_id == "uptime_kuma_monitors":
        run_command(["make", "generate-uptime-kuma-monitors"], repo_root=repo_root)
    elif artifact_id == "gate_bypass_keep":
        path.parent.mkdir(parents=True, exist_ok=True)
        if not artifact_ready(artifact_id, repo_root=repo_root):
            path.write_text("# fresh-worktree bootstrap sentinel\n", encoding="utf-8")
    elif artifact_id == "drift_reports_dir":
        path.mkdir(parents=True, exist_ok=True)
    elif artifact_id == "image_scan_receipts":
        source_root = find_primary_worktree(repo_root)
        source = source_root / "receipts" / "image-scans"
        if not source.exists():
            raise RuntimeError(f"missing source image scan receipts at {source}")
        path.mkdir(parents=True, exist_ok=True)
        if source.resolve() == path.resolve():
            return path
        for entry in source.iterdir():
            target = path / entry.name
            if entry.is_dir():
                copytree(entry, target, dirs_exist_ok=True)
            else:
                copy2(entry, target)
    else:
        raise KeyError(f"unknown artifact '{artifact_id}'")

    if not artifact_ready(artifact_id, repo_root=repo_root):
        raise RuntimeError(f"{artifact_id} materialized but {path} is still not ready")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize generated live-apply artifacts needed by fresh worktrees."
    )
    parser.add_argument(
        "--artifact",
        action="append",
        choices=sorted(ARTIFACTS),
        required=True,
        help="Artifact id to materialize. May be passed multiple times.",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()

    for artifact_id in args.artifact:
        target = materialize_artifact(artifact_id, repo_root=repo_root)
        print(f"PASS {artifact_id}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
