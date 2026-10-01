#!/usr/bin/env python3
"""Restore missing Dify host secret files from the current rendered runtime env.

This is intentionally fail-closed: existing non-empty secret files must match
the current OpenBao-rendered runtime environment or the converge stops before
the generic secret manager can mirror stale values back to OpenBao.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path


SECRET_FILES = {
    "INIT_PASSWORD": "init-password.txt",
    "SECRET_KEY": "secret-key.txt",
    "REDIS_PASSWORD": "redis-password.txt",
    "QDRANT_API_KEY": "qdrant-api-key.txt",
    "SANDBOX_API_KEY": "sandbox-api-key.txt",
    "PLUGIN_DAEMON_KEY": "plugin-daemon-key.txt",
    "PLUGIN_DIFY_INNER_API_KEY": "plugin-inner-api-key.txt",
    "TOOLS_API_KEY": "tools-api-key.txt",
}

REQUIRED_ENV_KEYS = frozenset(
    {
        *(SECRET_FILES.keys() - {"TOOLS_API_KEY"}),
        "SERVER_KEY",
        "DIFY_INNER_API_KEY",
        "INNER_API_KEY_FOR_PLUGIN",
    }
)

ALIASES = (
    ("SERVER_KEY", "PLUGIN_DAEMON_KEY"),
    ("DIFY_INNER_API_KEY", "PLUGIN_DIFY_INNER_API_KEY"),
    ("INNER_API_KEY_FOR_PLUGIN", "PLUGIN_DIFY_INNER_API_KEY"),
)


class SeedError(Exception):
    """A safe-to-display error that never contains a secret value."""


def _read_runtime_env(env_file: Path) -> dict[str, bytes] | None:
    try:
        env_stat = env_file.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(env_stat.st_mode):
        raise SeedError("runtime env is not a regular file")

    try:
        raw_env = env_file.read_bytes()
    except OSError as exc:
        raise SeedError("runtime env could not be read") from exc

    values: dict[str, bytes] = {}
    for line in raw_env.splitlines():
        if not line or line.lstrip().startswith(b"#"):
            continue
        key_bytes, separator, value = line.partition(b"=")
        if not separator:
            raise SeedError("runtime env contains a malformed line")
        try:
            key = key_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise SeedError("runtime env contains an invalid key") from exc
        if key not in REQUIRED_ENV_KEYS:
            continue
        if key in values:
            raise SeedError(f"runtime env contains a duplicate {key} entry")
        if not value or value != value.strip() or b"\x00" in value:
            raise SeedError(f"runtime env contains an invalid {key} value")
        values[key] = value

    missing = sorted(REQUIRED_ENV_KEYS - values.keys())
    if missing:
        raise SeedError("runtime env is missing required Dify secret entries")
    for alias, canonical in ALIASES:
        if values[alias] != values[canonical]:
            raise SeedError(f"runtime env has inconsistent {alias} and {canonical} entries")
    return values


def _read_existing_secret(path: Path) -> bytes | None:
    try:
        file_stat = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(file_stat.st_mode):
        raise SeedError(f"existing secret target is not a regular file: {path.name}")
    if file_stat.st_size == 0:
        raise SeedError(f"existing secret target is empty: {path.name}")
    if stat.S_IMODE(file_stat.st_mode) & 0o077:
        raise SeedError(f"existing secret target has permissive mode: {path.name}")
    try:
        return path.read_bytes().rstrip(b"\r\n")
    except OSError as exc:
        raise SeedError(f"existing secret target could not be read: {path.name}") from exc


def _create_secret_without_overwrite(path: Path, value: bytes) -> bool:
    """Atomically create a 0600 file, returning False if another file exists."""
    fd, temp_name = tempfile.mkstemp(prefix=".dify-secret-seed-", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as temp_file:
            temp_file.write(value + b"\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError:
            return False
        return True
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def seed_runtime_secrets(env_file: Path, secret_dir: Path) -> tuple[int, int, bool]:
    """Seed missing targets and verify all existing targets against runtime env."""
    env_values = _read_runtime_env(env_file)
    if env_values is None:
        return 0, 0, False

    try:
        dir_stat = secret_dir.lstat()
    except OSError as exc:
        raise SeedError("Dify secret directory is unavailable") from exc
    if not stat.S_ISDIR(dir_stat.st_mode):
        raise SeedError("Dify secret path is not a directory")

    planned_creates: list[tuple[Path, bytes]] = []
    existing = 0
    for env_key, filename in SECRET_FILES.items():
        target = secret_dir / filename
        current = _read_existing_secret(target)
        if env_key not in env_values:
            if current is None:
                raise SeedError(f"runtime env does not carry this secret and host source is missing: {filename}")
            existing += 1
            continue
        if current is not None:
            if current != env_values[env_key]:
                raise SeedError(f"existing secret does not match runtime env: {filename}")
            existing += 1
            continue
        planned_creates.append((target, env_values[env_key]))

    created = 0
    for target, expected in planned_creates:
        if _create_secret_without_overwrite(target, expected):
            created += 1
            continue
        # Another writer won the create race; accept only an identical file.
        current = _read_existing_secret(target)
        if current != expected:
            raise SeedError(f"existing secret does not match runtime env: {target.name}")
        existing += 1

    return created, existing, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--secret-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        created, existing, runtime_env_present = seed_runtime_secrets(args.env_file, args.secret_dir)
    except (SeedError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not runtime_env_present:
        print("runtime_env=absent created=0 existing=0")
        return 0
    print(f"runtime_env=present created={created} existing={existing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
