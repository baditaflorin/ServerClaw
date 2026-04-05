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

Exit codes
----------
  0   Success / change made
  1   Fatal error
  2   No-op / idempotent (nothing to migrate, key already present, etc.)

Note: Coolify-specific commands (db-exec, clear-cache, migrate-apps, install-deploy-key)
have moved to coolify_tool.py (ADR 0345).
"""

from __future__ import annotations

import argparse
import json
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

try:
    from controller_automation_toolkit import load_proxmox_auth as load_auth  # type: ignore[import]
except ImportError:
    # Toolkit additions from ADR 0343 not yet present; fall back to local implementation.
    load_auth = None  # type: ignore[assignment]

try:
    from controller_automation_toolkit import load_topology_snapshot  # type: ignore[import]
except ImportError:
    load_topology_snapshot = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_REQUIRED_AUTH_KEYS = {"api_url", "authorization_header"}


if load_auth is None:
    def load_auth(auth_file: str) -> dict:  # type: ignore[misc]
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


def _resolve_topology(
    args: argparse.Namespace, auth: dict
) -> dict:
    """
    Merge topology from four sources (lowest to highest priority):
      1. Hardcoded defaults
      2. auth file 'topology' key (if present — legacy single-env support)
      3. topology snapshot (ADR 0344) — auto-discovered from scripts/topology-snapshot.json,
         or explicit --topology-file if given (preferred over old YAML format)
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

    # Layer 2: topology snapshot (ADR 0344) — auto-discovered if no explicit file given
    topo_file = getattr(args, "topology_file", None)
    env = getattr(args, "env", "prod")
    snapshot_default = Path(__file__).parent / "topology-snapshot.json"
    effective_snapshot = topo_file or (str(snapshot_default) if snapshot_default.exists() else None)
    if effective_snapshot and load_topology_snapshot is not None:
        snapshot_topo = load_topology_snapshot(effective_snapshot, env)
        # Map snapshot VM entries to flat topology keys
        vms = snapshot_topo.get("vms", {})
        if "coolify-lv3" in vms:
            topo["coolify_vmid"] = vms["coolify-lv3"].get("vmid", topo["coolify_vmid"])
        if "coolify-apps-lv3" in vms:
            topo["coolify_apps_vmid"] = vms["coolify-apps-lv3"].get("vmid", topo["coolify_apps_vmid"])
        services = snapshot_topo.get("services", {})
        if "coolify" in services:
            svc = services["coolify"]
            topo.setdefault("coolify_db_container", svc.get("db_container", topo["coolify_db_container"]))
            topo.setdefault("coolify_db_user", svc.get("db_user", topo["coolify_db_user"]))
            topo.setdefault("coolify_container", svc.get("app_container", topo["coolify_container"]))
        if "api_url" in snapshot_topo and "api_url" not in auth:
            topo["api_url"] = snapshot_topo["api_url"]
    elif topo_file:
        # Fallback: explicit topology-file in old YAML format
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


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _add_topology_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared --topology-file / --env / --node args to a sub-parser."""
    parser.add_argument(
        "--topology-file",
        metavar="FILE",
        help=(
            "Path to a topology snapshot JSON (ADR 0344, preferred) or legacy YAML file. "
            "If omitted, scripts/topology-snapshot.json is used automatically when present."
        ),
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
        help=(
            "Path to a topology snapshot JSON (ADR 0344, preferred) or legacy YAML file. "
            "If omitted, scripts/topology-snapshot.json is used automatically when present."
        ),
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

    return parser


_COMMAND_HANDLERS = {
    "guest-exec": command_guest_exec,
    "docker-ps": command_docker_ps,
    "install-key": command_install_key,
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
