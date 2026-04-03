#!/usr/bin/env python3
"""
proxmox_tool.py — Proxmox QEMU guest-agent automation for LV3 platform operators.

Eliminates manual `ssh florin 'sudo qm guest exec ...'` invocations by driving the
Proxmox REST API directly from the controller.  Zero SSH required; works through any
network path that can reach the Proxmox API (Tailscale, VPN, direct).

Designed for multi-environment deployments (dev / staging / prod): use --env to select
a topology section from the topology file, and keep a separate auth token per environment.

Auth file  (.local/proxmox-api/lv3-automation-<env>.json)
----------------------------------------------------------
Uses the same schema written by the proxmox_security / proxmox_api_token Ansible roles:

  {
    "api_url":              "https://proxmox.lv3.org:8006/api2/json",
    "full_token_id":        "lv3-automation@pve!primary",
    "value":                "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "authorization_header": "PVEAPIToken=lv3-automation@pve!primary=<secret>"
  }

Topology file  (.local/proxmox-api/topology.yaml)
--------------------------------------------------
Maps environment names to VM topology and container names:

  prod:
    node: pve
    coolify_vmid: 170
    coolify_apps_vmid: 171
    coolify_db_container: coolify-db
    coolify_db_user: coolify
    coolify_container: coolify
  staging:
    node: pve
    coolify_vmid: 180
    coolify_apps_vmid: 181
    coolify_db_container: coolify-db
    coolify_db_user: coolify
    coolify_container: coolify

Commands
--------
  guest-exec             Run an arbitrary shell command inside a VM (no SSH needed).
  docker-ps              List running Docker containers on a VM.
  install-key            Append a public SSH key to /root/.ssh/authorized_keys on a VM.
  coolify-db-exec        Execute a SQL statement in the Coolify Postgres container.
  coolify-clear-cache    Clear Coolify application + config cache.
  coolify-migrate-apps   Migrate Coolify app destination_id in the DB (bypasses API limit).
  coolify-install-deploy-key  Install the Coolify SSH deploy key on a target VM.

Exit codes
----------
  0   Success / change made
  1   Fatal error
  2   No-op / idempotent (nothing to migrate, key already present, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml  # optional — only needed for topology files
except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Auth + topology
# ---------------------------------------------------------------------------

_REQUIRED_AUTH_KEYS = {"api_url", "authorization_header"}


def load_auth(auth_file: str) -> dict:
    """
    Load a Proxmox API token file.  Accepts the schema written by the
    proxmox_security role: must contain api_url and authorization_header.

    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if required keys are missing.
    """
    path = Path(auth_file).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Proxmox auth file not found: {auth_file}")
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = _REQUIRED_AUTH_KEYS - set(data)
    if missing:
        raise ValueError(
            f"Proxmox auth file '{auth_file}' is missing required keys: "
            + ", ".join(sorted(missing))
        )
    return data


def load_topology(topology_file: str, env: str) -> dict:
    """
    Load the topology section for *env* from a YAML topology file.

    Returns an empty dict if the file does not exist (allows pure-CLI operation).
    Raises ValueError if the env key is not present in the file.
    """
    path = Path(topology_file).expanduser()
    if not path.exists():
        return {}
    if _yaml is None:
        raise ImportError(
            "PyYAML is required to read topology files: pip install pyyaml"
        )
    data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if env not in data:
        raise ValueError(
            f"Environment '{env}' not found in topology file '{topology_file}'. "
            f"Available: {', '.join(sorted(data))}"
        )
    return data[env]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ProxmoxClient:
    """
    Minimal Proxmox REST API client backed by stdlib urllib (no third-party deps).

    Authenticates via the pre-formatted authorization_header from the token file
    (PVEAPIToken=<id>=<secret>).  All responses are unwrapped from the {"data":…} envelope.
    """

    def __init__(
        self,
        api_url: str,
        authorization_header: str,
        node: str = "pve",
        verify_ssl: bool = False,
    ) -> None:
        # api_url already ends with /api2/json from the role-generated file
        self.api_base = api_url.rstrip("/")
        self.authorization_header = authorization_header
        self.node = node
        self.verify_ssl = verify_ssl

    def _request(self, method: str, path: str, payload: dict | None = None) -> Any:
        """Send a request to the Proxmox API and unwrap the data envelope."""
        url = f"{self.api_base}{path}"
        headers = {
            "Authorization": self.authorization_header,
            "Content-Type": "application/json",
        }
        body = json.dumps(payload).encode() if payload is not None else None
        ctx = (
            ssl.create_default_context()
            if self.verify_ssl
            else ssl._create_unverified_context()
        )
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                raw = json.loads(resp.read().decode())
                return raw.get("data", raw)
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise RuntimeError(
                f"Proxmox API {method} {path} → HTTP {exc.code}: {body_text}"
            ) from exc

    def guest_exec(
        self,
        vmid: int,
        command: list[str],
        timeout: int = 60,
    ) -> tuple[int, str, str]:
        """
        Execute a command inside a VM via the QEMU guest agent.

        Sends POST /agent/exec, then polls /agent/exec-status until the process
        exits or the timeout expires.

        Returns:
            (exit_code, stdout, stderr) — both strings are stripped of trailing whitespace.

        Raises TimeoutError if the command does not finish within *timeout* seconds.
        """
        exec_path = f"/nodes/{self.node}/qemu/{vmid}/agent/exec"
        result = self._request("POST", exec_path, payload={"command": command})
        pid = result["pid"]

        status_path = f"/nodes/{self.node}/qemu/{vmid}/agent/exec-status?pid={pid}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self._request("GET", status_path)
            if status.get("exited"):
                return (
                    int(status.get("exitcode", 0)),
                    status.get("out-data", ""),
                    status.get("err-data", ""),
                )
            time.sleep(0.5)
        raise TimeoutError(
            f"Command in VM {vmid} (pid={pid}) did not complete within {timeout}s"
        )


def _make_client(
    auth: dict, node: str = "pve", api_url_override: str | None = None
) -> ProxmoxClient:
    return ProxmoxClient(
        api_url=api_url_override or auth["api_url"],
        authorization_header=auth["authorization_header"],
        node=node,
        verify_ssl=auth.get("verify_ssl", False),
    )


def _client_from_args(
    args: argparse.Namespace, auth: dict, topo: dict
) -> ProxmoxClient:
    """Build a ProxmoxClient from resolved auth + topology + optional --api-url override.

    API URL priority (highest wins):
      1. --api-url CLI flag
      2. topology['api_url'] (set per-env in topology.yaml for Tailscale / VPN access paths)
      3. auth file api_url (usually the public hostname — may not be reachable from controller)
    """
    return _make_client(
        auth,
        node=str(topo.get("node", "pve")),
        api_url_override=getattr(args, "api_url", None) or topo.get("api_url"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE_IDENT_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _safe_identifier(value: str, field: str) -> str:
    """Validate *value* as a safe SQL identifier (alphanumeric, dash, underscore).

    Prevents SQL injection in the coolify-migrate-apps server name queries.
    """
    if not _SAFE_IDENT_RE.match(value):
        raise ValueError(
            f"Unsafe value for {field}: {value!r} "
            "(only alphanumeric, dash, and underscore are allowed)"
        )
    return value


def _psql_query(
    client: ProxmoxClient,
    vmid: int,
    container: str,
    db_user: str,
    sql: str,
    timeout: int = 30,
) -> str:
    """Run a SQL query in a Postgres container and return stripped stdout.

    Uses psql -t -A (tuple-only, unaligned) for clean programmatic output.
    Raises RuntimeError if the command exits non-zero.
    """
    exit_code, stdout, stderr = client.guest_exec(
        vmid,
        ["docker", "exec", container, "psql", "-U", db_user, "-t", "-A", "-c", sql],
        timeout=timeout,
    )
    if exit_code != 0:
        raise RuntimeError(
            f"psql query failed (exit {exit_code}): {stderr.strip() or stdout.strip()}"
        )
    return stdout.strip()


def _resolve_topology(
    args: argparse.Namespace, auth: dict
) -> dict:
    """
    Merge topology from three sources (lowest to highest priority):
      1. Hardcoded defaults
      2. auth file 'topology' key (if present — legacy single-env support)
      3. topology file keyed by --env (if --topology-file is provided)
      4. Explicit CLI flags on args

    Returns a dict with the resolved topology values.
    """
    topo: dict = {
        "node": "pve",
        "coolify_vmid": 0,
        "coolify_apps_vmid": 0,
        "coolify_db_container": "coolify-db",
        "coolify_db_user": "coolify",
        "coolify_container": "coolify",
    }
    # Layer 1: topology key embedded in auth file (backward compat)
    topo.update(auth.get("topology", {}))

    # Layer 2: topology file
    topo_file = getattr(args, "topology_file", None)
    env = getattr(args, "env", "prod")
    if topo_file:
        topo.update(load_topology(topo_file, env))

    # Layer 3: explicit CLI overrides
    for cli_key, topo_key in (
        ("node", "node"),
        ("coolify_vmid", "coolify_vmid"),
        ("coolify_apps_vmid", "coolify_apps_vmid"),
        ("container", "coolify_db_container"),
        ("coolify_container", "coolify_container"),
        ("db_user", "coolify_db_user"),
    ):
        val = getattr(args, cli_key, None)
        if val is not None:
            topo[topo_key] = val

    return topo


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def command_guest_exec(args: argparse.Namespace) -> int:
    """
    Run an arbitrary shell command inside a VM via the QEMU guest agent.

    No SSH access to the guest is required.  The command is executed as root
    (the QEMU guest agent runs as root on the guest).

    Output: JSON with vmid, exit_code, stdout, stderr.
    Exit code: 0 on success, 1 on tool error.
    Use --propagate-exit-code to forward the guest command's exit code.
    """
    auth = load_auth(args.auth_file)
    topo = _resolve_topology(args, auth)
    client = _client_from_args(args, auth, topo)

    cmd_args: list[str] = list(args.command_args)
    if cmd_args and cmd_args[0] == "--":
        cmd_args = cmd_args[1:]
    if not cmd_args:
        print(json.dumps({"error": "No command specified after guest-exec"}), file=sys.stderr)
        return 1

    if args.shell:
        cmd: list[str] = ["bash", "-c", " ".join(cmd_args)]
    else:
        cmd = cmd_args

    exit_code, stdout, stderr = client.guest_exec(
        int(args.vmid), cmd, timeout=args.timeout
    )
    result = {
        "vmid": int(args.vmid),
        "exit_code": exit_code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }
    print(json.dumps(result, indent=2))
    return exit_code if args.propagate_exit_code else (0 if exit_code == 0 else 1)


def command_docker_ps(args: argparse.Namespace) -> int:
    """
    List running Docker containers on a VM as a JSON array.

    Uses `docker ps --format '{{json .}}'` via the QEMU guest agent.
    Output: JSON with vmid and a containers array.
    """
    auth = load_auth(args.auth_file)
    topo = _resolve_topology(args, auth)
    client = _client_from_args(args, auth, topo)
    vmid = int(args.vmid)

    exit_code, stdout, stderr = client.guest_exec(
        vmid,
        ["docker", "ps", "--format", "{{json .}}"],
        timeout=30,
    )
    if exit_code != 0:
        print(
            json.dumps({"error": stderr.strip(), "exit_code": exit_code}),
            file=sys.stderr,
        )
        return 1
    containers = [
        json.loads(line)
        for line in stdout.strip().splitlines()
        if line.strip()
    ]
    print(json.dumps({"vmid": vmid, "containers": containers}, indent=2))
    return 0


def command_install_key(args: argparse.Namespace) -> int:
    """
    Append a public SSH key to /root/.ssh/authorized_keys on a VM.

    Idempotent: if the key fingerprint is already in authorized_keys the
    command exits 2 (no-op) without modifying the file.
    Creates ~/.ssh with mode 700 and the file with mode 600 if absent.

    Output: JSON with vmid, status ('installed' or 'already_present'),
    and key_fingerprint (the comment field from the public key).
    """
    auth = load_auth(args.auth_file)
    topo = _resolve_topology(args, auth)
    client = _client_from_args(args, auth, topo)
    vmid = int(args.vmid)
    pubkey = args.pubkey.strip()

    # Read current authorized_keys (create empty string if absent)
    _, existing, _ = client.guest_exec(
        vmid,
        ["bash", "-c", "cat /root/.ssh/authorized_keys 2>/dev/null || true"],
        timeout=15,
    )

    key_comment = pubkey.split()[-1] if len(pubkey.split()) >= 3 else ""

    if pubkey in existing:
        result = {
            "vmid": vmid,
            "status": "already_present",
            "key_fingerprint": key_comment,
        }
        print(json.dumps(result, indent=2))
        return 2  # idempotent no-op

    script = (
        "mkdir -p /root/.ssh && "
        "chmod 700 /root/.ssh && "
        f"echo {shlex.quote(pubkey)} >> /root/.ssh/authorized_keys && "
        "chmod 600 /root/.ssh/authorized_keys"
    )
    exit_code, _, stderr = client.guest_exec(
        vmid, ["bash", "-c", script], timeout=15
    )
    if exit_code != 0:
        print(
            json.dumps({"error": stderr.strip(), "exit_code": exit_code}),
            file=sys.stderr,
        )
        return 1
    result = {
        "vmid": vmid,
        "status": "installed",
        "key_fingerprint": key_comment,
    }
    print(json.dumps(result, indent=2))
    return 0


def command_coolify_db_exec(args: argparse.Namespace) -> int:
    """
    Execute a SQL statement in the Coolify Postgres container on a given VM.

    Runs: docker exec <container> psql -U <user> -c '<sql>'

    Output: JSON with vmid, container, sql, exit_code, stdout, stderr.
    """
    auth = load_auth(args.auth_file)
    topo = _resolve_topology(args, auth)
    client = _client_from_args(args, auth, topo)

    vmid = int(topo.get("coolify_vmid") or 0)
    if not vmid:
        print(
            json.dumps({"error": "--coolify-vmid (or topology.coolify_vmid) is required"}),
            file=sys.stderr,
        )
        return 1

    container = str(topo["coolify_db_container"])
    db_user = str(topo["coolify_db_user"])

    exit_code, stdout, stderr = client.guest_exec(
        vmid,
        ["docker", "exec", container, "psql", "-U", db_user, "-c", args.sql],
        timeout=args.timeout,
    )
    result = {
        "vmid": vmid,
        "container": container,
        "sql": args.sql,
        "exit_code": exit_code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }
    print(json.dumps(result, indent=2))
    return 0 if exit_code == 0 else 1


def command_coolify_clear_cache(args: argparse.Namespace) -> int:
    """
    Clear the Coolify application and config cache on the control-plane VM.

    Equivalent to: docker exec coolify bash -c
      'cd /var/www/html && php artisan cache:clear && php artisan config:clear'

    Run this after any direct database change to ensure Coolify picks up the
    new state without requiring a container restart.
    """
    auth = load_auth(args.auth_file)
    topo = _resolve_topology(args, auth)
    client = _client_from_args(args, auth, topo)

    vmid = int(topo.get("coolify_vmid") or 0)
    if not vmid:
        print(
            json.dumps({"error": "--coolify-vmid (or topology.coolify_vmid) is required"}),
            file=sys.stderr,
        )
        return 1

    container = str(topo["coolify_container"])
    script = "cd /var/www/html && php artisan cache:clear && php artisan config:clear"
    exit_code, stdout, stderr = client.guest_exec(
        vmid,
        ["docker", "exec", container, "bash", "-c", script],
        timeout=60,
    )
    result = {
        "vmid": vmid,
        "container": container,
        "exit_code": exit_code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }
    print(json.dumps(result, indent=2))
    return 0 if exit_code == 0 else 1


def command_coolify_migrate_apps(args: argparse.Namespace) -> int:
    """
    Migrate Coolify application destination_id from one server to another via direct
    DB update — bypassing the Coolify API v1 limitation (PATCH /applications rejects
    server_uuid and destination_uuid with HTTP 422).

    Workflow
    --------
    1. Resolve standalone_docker destination IDs from server names (JOIN query).
    2. Count apps on the source destination.  Exit 2 (no-op) if count == 0.
    3. List app names for result reporting.
    4. UPDATE applications SET destination_id = <to_id> WHERE destination_id = <from_id>
    5. Clear Coolify application + config cache.

    Idempotent: calling this when apps are already on the target server exits 2.
    Use --dry-run to preview what would be migrated without making changes.

    Multi-env: pass --topology-file + --env to select the right Coolify VMID.
    """
    auth = load_auth(args.auth_file)
    topo = _resolve_topology(args, auth)
    client = _client_from_args(args, auth, topo)

    vmid = int(topo.get("coolify_vmid") or 0)
    if not vmid:
        print(
            json.dumps({"error": "--coolify-vmid (or topology.coolify_vmid) is required"}),
            file=sys.stderr,
        )
        return 1

    db_container = str(topo["coolify_db_container"])
    app_container = str(topo["coolify_container"])
    db_user = str(topo["coolify_db_user"])

    from_name = _safe_identifier(args.from_server, "--from")
    to_name = _safe_identifier(args.to_server, "--to")

    # Step 1: Resolve destination IDs from server names
    from_sql = (
        f"SELECT sd.id FROM standalone_dockers sd "
        f"JOIN servers s ON s.id = sd.server_id "
        f"WHERE s.name = '{from_name}' LIMIT 1"
    )
    to_sql = (
        f"SELECT sd.id FROM standalone_dockers sd "
        f"JOIN servers s ON s.id = sd.server_id "
        f"WHERE s.name = '{to_name}' LIMIT 1"
    )

    from_id_str = _psql_query(client, vmid, db_container, db_user, from_sql)
    to_id_str = _psql_query(client, vmid, db_container, db_user, to_sql)

    missing: list[str] = []
    if not from_id_str:
        missing.append(f"source server '{from_name}'")
    if not to_id_str:
        missing.append(f"target server '{to_name}'")
    if missing:
        print(
            json.dumps(
                {"error": f"Could not find standalone_docker destination for: {', '.join(missing)}"}
            ),
            file=sys.stderr,
        )
        return 1

    from_id = int(from_id_str)
    to_id = int(to_id_str)

    # Step 2: Count apps on source
    count_str = _psql_query(
        client, vmid, db_container, db_user,
        f"SELECT count(*) FROM applications WHERE destination_id = {from_id}",
    )
    count = int(count_str) if count_str.isdigit() else 0

    if count == 0:
        result = {
            "status": "nothing_to_migrate",
            "from_server": from_name,
            "to_server": to_name,
            "from_destination_id": from_id,
            "to_destination_id": to_id,
            "migrated_count": 0,
            "migrated_apps": [],
        }
        print(json.dumps(result, indent=2))
        return 2

    # Step 3: List app names
    names_raw = _psql_query(
        client, vmid, db_container, db_user,
        f"SELECT name FROM applications WHERE destination_id = {from_id}",
    )
    app_names = [n.strip() for n in names_raw.splitlines() if n.strip()]

    # Step 4: Run the migration (skipped in dry-run mode)
    if not args.dry_run:
        _psql_query(
            client, vmid, db_container, db_user,
            f"UPDATE applications SET destination_id = {to_id} WHERE destination_id = {from_id}",
        )

        # Step 5: Clear Coolify cache so changes take effect immediately
        cache_script = (
            "cd /var/www/html && php artisan cache:clear && php artisan config:clear"
        )
        cache_rc, _, cache_err = client.guest_exec(
            vmid,
            ["docker", "exec", app_container, "bash", "-c", cache_script],
            timeout=60,
        )
        if cache_rc != 0:
            # Non-fatal: migration is done, cache miss is recoverable
            print(
                json.dumps(
                    {"warning": f"Migration succeeded but cache clear failed: {cache_err.strip()}"}
                ),
                file=sys.stderr,
            )

    result = {
        "status": "dry_run" if args.dry_run else "migrated",
        "from_server": from_name,
        "to_server": to_name,
        "from_destination_id": from_id,
        "to_destination_id": to_id,
        "migrated_count": count,
        "migrated_apps": app_names,
    }
    print(json.dumps(result, indent=2))
    return 0


def command_coolify_install_deploy_key(args: argparse.Namespace) -> int:
    """
    Install the Coolify SSH deploy public key on a target VM.

    Coolify needs to SSH into deployment servers using its own deploy key.
    This command installs that key into /root/.ssh/authorized_keys on the
    target VM so that server validation and deployment succeed.

    The deploy key can be found in the Coolify UI under Settings > SSH Keys,
    or from the Coolify bootstrap artifacts at .local/coolify/deploy-key.pub.

    Delegates to install-key internally.  Exits 2 if already present.
    """
    return command_install_key(args)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _add_topology_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared --topology-file / --env / --node args to a sub-parser."""
    parser.add_argument(
        "--topology-file",
        metavar="FILE",
        help="Path to topology YAML file (.local/proxmox-api/topology.yaml).",
    )
    parser.add_argument(
        "--env",
        default="prod",
        metavar="ENV",
        help="Environment key to select from the topology file (default: prod).",
    )
    parser.add_argument(
        "--node",
        metavar="NODE",
        help="Proxmox node name (default: pve or topology value).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proxmox_tool.py",
        description=(
            "Proxmox QEMU guest-agent automation — run commands in VMs without SSH, "
            "manage authorized_keys, and perform Coolify DB operations programmatically."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--auth-file",
        required=True,
        metavar="FILE",
        help="Path to Proxmox API token JSON file (.local/proxmox-api/lv3-automation-primary.json).",
    )
    parser.add_argument(
        "--topology-file",
        metavar="FILE",
        help="Path to topology YAML file (.local/proxmox-api/topology.yaml).",
    )
    parser.add_argument(
        "--env",
        default="prod",
        metavar="ENV",
        help="Environment key to select from the topology file (default: prod).",
    )
    parser.add_argument(
        "--node",
        metavar="NODE",
        help="Proxmox node name override (default: pve or topology value).",
    )
    parser.add_argument(
        "--api-url",
        metavar="URL",
        help=(
            "Override the api_url from the auth file "
            "(e.g. https://100.64.0.1:8006/api2/json for Tailscale access)."
        ),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- guest-exec ---
    p_exec = sub.add_parser(
        "guest-exec",
        help="Run a command inside a VM via QEMU guest agent (no SSH required).",
        description=(
            "Executes a command as root inside the VM.  "
            "Separate the tool arguments from the guest command with --."
        ),
    )

    p_exec.add_argument("--vmid", required=True, type=int, help="Target VMID.")
    p_exec.add_argument(
        "--timeout", type=int, default=60, help="Exec timeout in seconds (default: 60)."
    )
    p_exec.add_argument(
        "--shell",
        action="store_true",
        help="Wrap the command in bash -c (enables shell features like pipes).",
    )
    p_exec.add_argument(
        "--propagate-exit-code",
        action="store_true",
        help="Return the guest command exit code as the tool exit code.",
    )
    p_exec.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="Command and arguments to run in the VM.",
    )

    # --- docker-ps ---
    p_dps = sub.add_parser(
        "docker-ps",
        help="List running Docker containers on a VM.",
    )
    p_dps.add_argument("--vmid", required=True, type=int, help="Target VMID.")

    # --- install-key ---
    p_key = sub.add_parser(
        "install-key",
        help="Append a public SSH key to /root/.ssh/authorized_keys on a VM.",
    )
    p_key.add_argument("--vmid", required=True, type=int, help="Target VMID.")
    p_key.add_argument(
        "--pubkey", required=True, help="Public key string (e.g. 'ssh-ed25519 AAAA... comment')."
    )

    # --- coolify-db-exec ---
    p_db = sub.add_parser(
        "coolify-db-exec",
        help="Execute a SQL statement in the Coolify Postgres container.",
    )
    p_db.add_argument(
        "--coolify-vmid",
        dest="coolify_vmid",
        type=int,
        help="VMID of the Coolify control-plane VM (overrides topology).",
    )
    p_db.add_argument(
        "--container", help="Postgres container name (default: coolify-db)."
    )
    p_db.add_argument("--db-user", help="Postgres user (default: coolify).")
    p_db.add_argument("--sql", required=True, help="SQL statement to execute.")
    p_db.add_argument(
        "--timeout", type=int, default=30, help="Exec timeout in seconds (default: 30)."
    )

    # --- coolify-clear-cache ---
    p_cc = sub.add_parser(
        "coolify-clear-cache",
        help="Clear Coolify application and config cache (run after direct DB changes).",
    )
    p_cc.add_argument(
        "--coolify-vmid",
        dest="coolify_vmid",
        type=int,
        help="VMID of the Coolify control-plane VM (overrides topology).",
    )
    p_cc.add_argument(
        "--coolify-container",
        dest="coolify_container",
        help="Coolify app container name (default: coolify).",
    )

    # --- coolify-migrate-apps ---
    p_migrate = sub.add_parser(
        "coolify-migrate-apps",
        help="Migrate Coolify app destination_id in the DB (bypasses API v1 limitation).",
        description=(
            "Resolves standalone_docker destination IDs from server names, "
            "runs the UPDATE, and clears the Coolify cache.  Idempotent."
        ),
    )
    p_migrate.add_argument(
        "--from",
        dest="from_server",
        required=True,
        metavar="SERVER_NAME",
        help="Source Coolify server name (e.g. coolify-lv3).",
    )
    p_migrate.add_argument(
        "--to",
        dest="to_server",
        required=True,
        metavar="SERVER_NAME",
        help="Target Coolify server name (e.g. coolify-apps-lv3).",
    )
    p_migrate.add_argument(
        "--coolify-vmid",
        dest="coolify_vmid",
        type=int,
        help="VMID of the Coolify control-plane VM (overrides topology).",
    )
    p_migrate.add_argument(
        "--container", help="Postgres container name (default: coolify-db)."
    )
    p_migrate.add_argument(
        "--coolify-container",
        dest="coolify_container",
        help="Coolify app container name for cache clear (default: coolify).",
    )
    p_migrate.add_argument("--db-user", help="Postgres user (default: coolify).")
    p_migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be migrated without making any changes.",
    )

    # --- coolify-install-deploy-key ---
    p_deploy_key = sub.add_parser(
        "coolify-install-deploy-key",
        help="Install the Coolify SSH deploy public key on a target VM.",
    )
    p_deploy_key.add_argument(
        "--vmid", required=True, type=int, help="Target VMID (e.g. coolify-apps-lv3 VMID)."
    )
    p_deploy_key.add_argument(
        "--pubkey",
        required=True,
        help="Coolify deploy public key string (from Coolify UI > Settings > SSH Keys).",
    )

    return parser


_COMMAND_HANDLERS = {
    "guest-exec": command_guest_exec,
    "docker-ps": command_docker_ps,
    "install-key": command_install_key,
    "coolify-db-exec": command_coolify_db_exec,
    "coolify-clear-cache": command_coolify_clear_cache,
    "coolify-migrate-apps": command_coolify_migrate_apps,
    "coolify-install-deploy-key": command_coolify_install_deploy_key,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        return _COMMAND_HANDLERS[args.command](args)
    except (FileNotFoundError, ValueError, ImportError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(json.dumps({"error": f"timeout: {exc}"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
