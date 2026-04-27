"""Advisory file lock for deployment-scoped operations — ADR 0442.

Two agents converging two different deployments must not block each other.
Two agents converging the *same* deployment must serialise so they don't
interleave SSH sessions to the same host.

The lock is held as a `flock(2)` exclusive lock on
`.local/deployments/<slug>/state/<kind>.lock`. The file's content records
PID, hostname, and ISO timestamp of the holder for human-readable error
messages. The lock is advisory: the kernel does not enforce it on
processes that don't ask for it.

Usage:

    from scripts.deployment_lock import deployment_lock

    with deployment_lock("prod", kind="converge"):
        run_converge(...)

If the lock is held, raises `DeploymentLocked` with a message naming
the holder.
"""

from __future__ import annotations

import errno
import fcntl
import os
import socket
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

# Import the module (not the symbol) so tests can monkeypatch
# scripts.deployment.DEPLOYMENTS_DIR and we pick up the override.
from scripts import deployment as _dep_module


class DeploymentLocked(Exception):
    """Raised when an advisory lock is already held."""


def _holder_summary(path: Path) -> str:
    try:
        return path.read_text().strip() or "(no holder metadata)"
    except OSError:
        return "(unreadable holder metadata)"


@contextmanager
def deployment_lock(slug: str, *, kind: str = "converge", wait_seconds: float = 0.0) -> Iterator[Path]:
    """Acquire an advisory lock for a (deployment, kind) pair.

    Args:
        slug: deployment slug
        kind: short identifier for the operation class — "converge",
              "generate", "migrate", etc. Different kinds are independent.
        wait_seconds: poll for at most this many seconds before giving up.
                      0 = fail immediately if held.

    Yields the lock file path so callers can record additional context.
    """
    state_dir = _dep_module.DEPLOYMENTS_DIR / slug / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / f"{kind}.lock"

    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + wait_seconds
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    raise DeploymentLocked(
                        f"Deployment {slug!r} {kind!r} lock is held by:\n"
                        f"  {_holder_summary(lock_path)}\n"
                        f"  ({lock_path})"
                    ) from exc
                time.sleep(0.5)

        # Stamp the lock file with our metadata so the next caller sees who's holding it.
        os.lseek(fd, 0, 0)
        os.ftruncate(fd, 0)
        stamp = (
            f"pid={os.getpid()} "
            f"host={socket.gethostname()} "
            f"user={os.environ.get('USER', '?')} "
            f"argv={' '.join(sys.argv)} "
            f"acquired={datetime.now(UTC).isoformat(timespec='seconds')}"
        )
        os.write(fd, stamp.encode())
        os.fsync(fd)
        try:
            yield lock_path
        finally:
            os.lseek(fd, 0, 0)
            os.ftruncate(fd, 0)
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
