#!/usr/bin/env python3
"""Provision an Outline API token by inserting directly into the Outline PostgreSQL database.

This script handles the full lifecycle of Outline API token provisioning:
  1. Generate a cryptographically random token in the ol_api_<38-hex> format
  2. Connect to the Outline PostgreSQL database via the configured DB URL
  3. Insert the token into the apiKeys table under the automation service account
  4. Write the token to .local/outline/admin-auth.json

Because Outline's /api/apiKeys.create endpoint requires a browser session (not an API
key), direct DB insertion is the only programmatic path. This is explicitly documented
in ADR 0364.

Usage:
    python scripts/provision_outline_api_token.py [--name NAME] [--dry-run]

Environment overrides (all optional):
    LV3_OUTLINE_DB_URL          - Postgres connection URL (default: read from container env)
    LV3_PROXMOX_HOST_ADDR       - Proxmox jump host IP (default: 10.10.10.1)
    LV3_BOOTSTRAP_SSH_PRIVATE_KEY - Path to bootstrap SSH key
    LV3_OUTLINE_HOST_IP         - docker-runtime-lv3 IP (default: 10.10.10.20)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LOCAL_ROOT = REPO_ROOT / ".local"

# Infrastructure defaults — match inventory/group_vars/all.yml
DEFAULT_PROXMOX_HOST = "10.10.10.1"
DEFAULT_OUTLINE_HOST = "10.10.10.20"
DEFAULT_POSTGRES_HOST = "10.10.10.50"
DEFAULT_OUTLINE_DB = "outline"
DEFAULT_OUTLINE_DB_USER = "outline"

# The automation service account created during initial Outline setup
AUTOMATION_USER_EMAIL = "outline.automation@localhost"
AUTOMATION_USER_QUERY = f"""
SELECT id FROM users
WHERE email = '{AUTOMATION_USER_EMAIL}' AND "deletedAt" IS NULL
LIMIT 1;
"""


def _ssh_key_path() -> str:
    env_key = os.environ.get("LV3_BOOTSTRAP_SSH_PRIVATE_KEY")
    if env_key:
        return env_key
    default = LOCAL_ROOT / "ssh" / "bootstrap.id_ed25519"
    if default.is_file():
        return str(default)
    raise RuntimeError(
        "No SSH key found. Set LV3_BOOTSTRAP_SSH_PRIVATE_KEY or ensure "
        ".local/ssh/bootstrap.id_ed25519 exists."
    )


def _run_psql(sql: str, db_password: str, dry_run: bool = False) -> str:
    """Run a psql command on the Outline database via SSH jump to docker-runtime-lv3."""
    proxmox_host = os.environ.get("LV3_PROXMOX_HOST_ADDR", DEFAULT_PROXMOX_HOST)
    outline_host = os.environ.get("LV3_OUTLINE_HOST_IP", DEFAULT_OUTLINE_HOST)
    ssh_key = _ssh_key_path()

    psql_cmd = (
        f"PGPASSWORD={db_password} psql "
        f"-h {DEFAULT_POSTGRES_HOST} "
        f"-U {DEFAULT_OUTLINE_DB_USER} "
        f"-d {DEFAULT_OUTLINE_DB} "
        f"-t -A "
        f"-c \"{sql}\""
    )
    ssh_cmd = [
        "ssh",
        "-i", ssh_key,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=15",
        "-J", f"root@{proxmox_host}",
        f"ops@{outline_host}",
        psql_cmd,
    ]

    if dry_run:
        print(f"[dry-run] Would run psql: {sql[:80]}...")
        return ""

    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"psql failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result.stdout.strip()


def _generate_token() -> tuple[str, str, str]:
    """Generate (token, sha256_hash, last4) in Outline ol_api_ format."""
    # ol_api_ + 38 hex chars — must match /^[\w]{38}$/ after prefix removal
    suffix = secrets.token_hex(19)  # 19 bytes = 38 hex chars, all [0-9a-f]
    token = f"ol_api_{suffix}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    last4 = token[-4:]
    return token, token_hash, last4


def _read_db_password() -> str:
    """Read the Outline database password from .local/outline/database-password.txt."""
    pw_file = LOCAL_ROOT / "outline" / "database-password.txt"
    if pw_file.is_file():
        return pw_file.read_text().strip()
    raise RuntimeError(
        f"Outline DB password not found at {pw_file}. "
        "Cannot provision token without database access."
    )


def provision(name: str = "agent-automation", dry_run: bool = False) -> str:
    """Provision a new Outline API token.

    Args:
        name: Human-readable name for the API key in Outline.
        dry_run: If True, print what would happen without making changes.

    Returns:
        The new API token string (ol_api_...).
    """
    db_password = _read_db_password()

    # Resolve the automation user ID
    user_id = _run_psql(AUTOMATION_USER_QUERY, db_password, dry_run=dry_run)
    if not dry_run and not user_id:
        raise RuntimeError(
            f"Automation user '{AUTOMATION_USER_EMAIL}' not found in Outline DB. "
            "Ensure the user exists before provisioning tokens."
        )
    if dry_run:
        user_id = "00000000-0000-0000-0000-000000000000"

    token, token_hash, last4 = _generate_token()
    key_id = str(uuid.uuid4())

    insert_sql = (
        f"INSERT INTO \\\"apiKeys\\\" "
        f"(id, name, secret, hash, last4, \\\"userId\\\", \\\"createdAt\\\", \\\"updatedAt\\\") "
        f"VALUES ("
        f"'{key_id}', "
        f"'{name}', "
        f"'{token}', "
        f"'{token_hash}', "
        f"'{last4}', "
        f"'{user_id}', "
        f"NOW(), NOW()"
        f");"
    )

    _run_psql(insert_sql, db_password, dry_run=dry_run)

    # Write to .local/outline/admin-auth.json
    auth_path = LOCAL_ROOT / "outline" / "admin-auth.json"
    auth_data = {
        "base_url": "https://wiki.localhost",
        "api_token": token,
    }
    if not dry_run:
        auth_path.write_text(json.dumps(auth_data, indent=2) + "\n")
        print(f"Token written to {auth_path}")
    else:
        print(f"[dry-run] Would write token to {auth_path}")

    return token


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name",
        default="agent-automation",
        help="Name for the API key in Outline (default: agent-automation)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without making changes",
    )
    args = parser.parse_args()

    try:
        token = provision(name=args.name, dry_run=args.dry_run)
        if not args.dry_run:
            print(f"Outline API token provisioned: {token[:20]}...{token[-4:]}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
