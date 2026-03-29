from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator


REPO_ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _git_common_dir(repo_root: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def default_state_path(
    *,
    env_var: str,
    repo_root: Path | None = None,
    state_subpath: str | os.PathLike[str],
) -> Path:
    override = os.environ.get(env_var, "").strip()
    if override:
        return Path(override).expanduser()
    base = repo_root or REPO_ROOT
    common_dir = _git_common_dir(base)
    subpath = Path(state_subpath)
    if common_dir is not None:
        return common_dir / subpath
    return base / ".local" / "state" / subpath


@contextmanager
def locked_json_state(
    state_path: Path,
    *,
    default_factory: Callable[[], dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    import fcntl

    lock_path = state_path.with_suffix(f"{state_path.suffix}.lock")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if state_path.exists():
                raw = state_path.read_text(encoding="utf-8").strip()
                state = json.loads(raw) if raw else default_factory()
            else:
                state = default_factory()
            yield state
            state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
