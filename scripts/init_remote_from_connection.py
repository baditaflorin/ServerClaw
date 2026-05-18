"""Single-deployment (ADR 0488) entry point to init_remote_ops_user.sh.

Reads `.local/connection.yml` for proxmox_host.* and guest_ssh.* and invokes
the existing init_remote_ops_user.sh shell script with the right env vars.

Replaces the multi-deployment overlay-mode path that read those values from
BOOTSTRAP_OVERLAY_* Make variables.

Exit codes:
  0  ops sudoer created (or already present)
  1  missing/invalid connection.yml
  2  init_remote_ops_user.sh exited non-zero
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ROOT = REPO_ROOT / ".local"
CONNECTION_PATH = LOCAL_ROOT / "connection.yml"
SSH_DIR = LOCAL_ROOT / "ssh"
INIT_SCRIPT = REPO_ROOT / "scripts" / "init_remote_ops_user.sh"


def _resolve_key(value: str) -> str:
    if value.startswith("/"):
        return value
    return str(SSH_DIR / value)


def main() -> int:
    if not CONNECTION_PATH.is_file():
        print(f"ERROR: {CONNECTION_PATH} not found. Run `make derive-deployment-files` first.", file=sys.stderr)
        return 1
    data = yaml.safe_load(CONNECTION_PATH.read_text()) or {}
    host = data.get("proxmox_host") or {}
    guest = data.get("guest_ssh") or {}

    for field in ("addr", "user", "key"):
        if not host.get(field):
            print(f"ERROR: connection.yml proxmox_host.{field} missing", file=sys.stderr)
            return 1

    env = os.environ.copy()
    env["REMOTE_HOST"] = str(host["addr"])
    env["REMOTE_ROOT_USER"] = str(host["user"])
    env["REMOTE_ROOT_KEY"] = _resolve_key(str(host["key"]))
    env["OPS_USER"] = str(guest.get("user", "ops"))
    env["OPS_PUBKEY_PATH"] = str(SSH_DIR / "bootstrap.id_ed25519.pub")
    env["OPS_PROBE_KEY"] = _resolve_key(str(guest.get("key", "bootstrap.id_ed25519")))

    print(
        f"init-remote: {env['REMOTE_ROOT_USER']}@{env['REMOTE_HOST']} "
        f"(root key: {env['REMOTE_ROOT_KEY']}) -> creates {env['OPS_USER']} sudoer",
        file=sys.stderr,
    )

    result = subprocess.run([str(INIT_SCRIPT)], env=env)
    return 2 if result.returncode else 0


if __name__ == "__main__":
    sys.exit(main())
