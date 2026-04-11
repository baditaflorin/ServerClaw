#!/usr/bin/env python3
"""Build immutable repository snapshots for remote validation and build runs."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
from dataclasses import asdict, dataclass
from datetime import datetime
try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone
    UTC = timezone.utc  # type: ignore[assignment]
from pathlib import Path
from typing import Any


DEFAULT_EXCLUDED_DIR_NAMES = {
    ".git",
    ".git-remote",
}


@dataclass(frozen=True)
class SnapshotEntry:
    path: str
    type: str
    sha256: str | None
    size: int | None
    link_target: str | None = None


@dataclass(frozen=True)
class SnapshotManifest:
    schema_version: int
    snapshot_id: str
    generated_at: str
    repo_root: str
    source_commit: str
    branch: str
    exclude_file: str | None
    entries: list[SnapshotEntry]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build an immutable repository snapshot.")
    build.add_argument("--repo-root", type=Path, default=Path.cwd())
    build.add_argument("--exclude-file", type=Path, help="Exclude-file with rsync-style simple patterns.")
    build.add_argument(
        "--output-dir", type=Path, required=True, help="Directory that receives the archive and manifest."
    )
    build.add_argument("--format", choices=("json", "shell"), default="json")

    return parser.parse_args(argv)


def git_value(repo_root: Path, *args: str, default: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return default
    value = completed.stdout.strip()
    return value or default


def load_exclude_patterns(exclude_file: Path | None) -> list[str]:
    if exclude_file is None or not exclude_file.exists():
        return []
    patterns: list[str] = []
    for raw_line in exclude_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _matches_segment_path(relative_path: str, segment_path: str) -> bool:
    parts = relative_path.split("/")
    segment_parts = segment_path.split("/")
    if len(segment_parts) > len(parts):
        return False
    for index in range(0, len(parts) - len(segment_parts) + 1):
        if parts[index : index + len(segment_parts)] == segment_parts:
            return True
    return False


def should_exclude(relative_path: str, *, is_dir: bool, patterns: list[str]) -> bool:
    parts = relative_path.split("/")
    if any(part in DEFAULT_EXCLUDED_DIR_NAMES for part in parts):
        return True

    basename = parts[-1]
    for pattern in patterns:
        if pattern.endswith("/"):
            dir_pattern = pattern.rstrip("/")
            if relative_path == dir_pattern or relative_path.startswith(f"{dir_pattern}/"):
                return True
            if _matches_segment_path(relative_path, dir_pattern):
                return True
            continue

        if "/" in pattern:
            if relative_path == pattern:
                return True
            if is_dir and relative_path.startswith(f"{pattern}/"):
                return True
            continue

        if basename == pattern:
            return True
        if pattern.startswith("*.") and basename.endswith(pattern[1:]):
            return True

    return False


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_entries(repo_root: Path, patterns: list[str]) -> list[SnapshotEntry]:
    entries: list[SnapshotEntry] = []
    for current_root, dirnames, filenames in os.walk(repo_root, topdown=True, followlinks=False):
        root_path = Path(current_root)
        rel_root = root_path.relative_to(repo_root)
        rel_root_str = "" if rel_root == Path(".") else rel_root.as_posix()

        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            rel_dir = f"{rel_root_str}/{dirname}" if rel_root_str else dirname
            full_dir = root_path / dirname
            if should_exclude(rel_dir, is_dir=True, patterns=patterns):
                continue
            if full_dir.is_symlink():
                entries.append(
                    SnapshotEntry(
                        path=rel_dir,
                        type="symlink",
                        sha256=None,
                        size=None,
                        link_target=os.readlink(full_dir),
                    )
                )
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            rel_file = f"{rel_root_str}/{filename}" if rel_root_str else filename
            full_file = root_path / filename
            if should_exclude(rel_file, is_dir=False, patterns=patterns):
                continue
            if full_file.is_symlink():
                entries.append(
                    SnapshotEntry(
                        path=rel_file,
                        type="symlink",
                        sha256=None,
                        size=None,
                        link_target=os.readlink(full_file),
                    )
                )
                continue
            entries.append(
                SnapshotEntry(
                    path=rel_file,
                    type="file",
                    sha256=file_sha256(full_file),
                    size=full_file.stat().st_size,
                )
            )
    return entries


def snapshot_id_for(*, source_commit: str, branch: str, entries: list[SnapshotEntry]) -> str:
    identity = {
        "source_commit": source_commit,
        "branch": branch,
        "entries": [asdict(entry) for entry in entries],
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def normalized_tarinfo(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
    tarinfo.uid = 0
    tarinfo.gid = 0
    tarinfo.uname = ""
    tarinfo.gname = ""
    tarinfo.mtime = 0
    return tarinfo


def write_archive(repo_root: Path, archive_path: Path, manifest: SnapshotManifest) -> None:
    with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for entry in manifest.entries:
            archive.add(
                str(repo_root / entry.path),
                arcname=f"repo/{entry.path}",
                recursive=False,
                filter=normalized_tarinfo,
            )

        manifest_bytes = (json.dumps(asdict(manifest), indent=2) + "\n").encode("utf-8")
        tarinfo = tarfile.TarInfo("metadata/manifest.json")
        tarinfo.size = len(manifest_bytes)
        tarinfo.mode = 0o644
        normalized_tarinfo(tarinfo)
        archive.addfile(tarinfo, io.BytesIO(manifest_bytes))


def shell_lines(payload: dict[str, Any]) -> str:
    return "\n".join(
        f"{key}={json.dumps(str(value) if isinstance(value, Path) else value)}" for key, value in payload.items()
    )


def build_snapshot(repo_root: Path, *, exclude_file: Path | None, output_dir: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    patterns = load_exclude_patterns(exclude_file.resolve() if exclude_file else None)
    entries = build_entries(repo_root, patterns)
    source_commit = git_value(repo_root, "rev-parse", "HEAD", default="unknown")
    branch_override = os.environ.get("LV3_SNAPSHOT_BRANCH", "").strip()
    branch = branch_override or git_value(repo_root, "rev-parse", "--abbrev-ref", "HEAD", default="detached")
    snapshot_id = snapshot_id_for(source_commit=source_commit, branch=branch, entries=entries)
    generated_at = datetime.now(UTC).isoformat()
    manifest = SnapshotManifest(
        schema_version=1,
        snapshot_id=snapshot_id,
        generated_at=generated_at,
        repo_root=str(repo_root),
        source_commit=source_commit,
        branch=branch,
        exclude_file=str(exclude_file.resolve()) if exclude_file else None,
        entries=entries,
    )

    manifest_path = output_dir / f"repository-snapshot-{snapshot_id}.json"
    archive_path = output_dir / f"repository-snapshot-{snapshot_id}.tar.gz"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2) + "\n", encoding="utf-8")
    write_archive(repo_root, archive_path, manifest)

    return {
        "LV3_SNAPSHOT_ID": snapshot_id,
        "LV3_SNAPSHOT_ARCHIVE": str(archive_path),
        "LV3_SNAPSHOT_MANIFEST": str(manifest_path),
        "LV3_SNAPSHOT_GENERATED_AT": generated_at,
        "LV3_SNAPSHOT_SOURCE_COMMIT": source_commit,
        "LV3_SNAPSHOT_BRANCH": branch,
        "LV3_SNAPSHOT_FILE_COUNT": len(entries),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command != "build":
        raise SystemExit(f"unsupported command: {args.command}")

    payload = build_snapshot(
        args.repo_root,
        exclude_file=args.exclude_file,
        output_dir=args.output_dir,
    )
    if args.format == "shell":
        print(shell_lines(payload))
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
