"""Resolve shared Plane auth and keep a configured private SSH tunnel alive."""

from __future__ import annotations

import json
import re
import socket
import subprocess
import time
import urllib.parse
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def plane_local_dir(repo_root: Path) -> Path:
    """Use a checkout's own overlay, otherwise the main worktree's overlay."""
    local = repo_root / ".local" / "plane"
    if (local / "admin-auth.json").is_file():
        return local
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"], cwd=repo_root, text=True, capture_output=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return local
    if result.returncode == 0:
        first = next((line[9:] for line in result.stdout.splitlines() if line.startswith("worktree ")), None)
        if first:
            shared = Path(first) / ".local" / "plane"
            if (shared / "admin-auth.json").is_file():
                return shared
    return local


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


@contextmanager
def plane_transport(auth_file: Path) -> Iterator[None]:
    """Start a loopback-only forward when the optional local transport config requires it."""
    config_file = auth_file.parent / "transport.json"
    if not config_file.is_file() or not auth_file.is_file():
        yield
        return
    config = json.loads(config_file.read_text(encoding="utf-8"))
    auth = json.loads(auth_file.read_text(encoding="utf-8"))
    url = urllib.parse.urlsplit(auth["base_url"])
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port:
        raise ValueError("Plane SSH transport requires an HTTP 127.0.0.1 base URL with an explicit port")
    if _listening(url.port):
        yield
        return
    target = config.get("ssh_target", "")
    remote_port = config.get("remote_port")
    if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", target):
        raise ValueError("Plane SSH transport has an invalid SSH target")
    if not isinstance(remote_port, int) or isinstance(remote_port, bool) or not 1 <= remote_port <= 65535:
        raise ValueError("Plane SSH transport has an invalid remote port")
    command = [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=30",
        "-L",
        f"127.0.0.1:{url.port}:127.0.0.1:{remote_port}",
        target,
        "cat >/dev/null",
    ]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while not _listening(url.port):
            if proc.poll() is not None:
                raise RuntimeError("Plane SSH tunnel failed to start; check the configured SSH target")
            if time.monotonic() >= deadline:
                raise RuntimeError("Plane SSH tunnel did not become ready")
            time.sleep(0.1)
        yield
    finally:
        if proc.stdin:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
