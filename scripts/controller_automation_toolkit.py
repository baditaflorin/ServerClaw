#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

loaded_platform = sys.modules.get("platform")
if loaded_platform is not None and not hasattr(loaded_platform, "__path__"):
    loaded_platform_file = getattr(loaded_platform, "__file__", "")
    if not str(loaded_platform_file).startswith(str(REPO_ROOT / "platform")):
        sys.modules.pop("platform", None)

from platform.repo import *  # noqa: F401,F403
from platform.repo import _load_yaml_without_pyyaml as repo_load_yaml_without_pyyaml


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def resolve_repo_local_path(path_value: str | Path, *, repo_root: Path = REPO_ROOT) -> Path:
    path = Path(path_value).expanduser()
    if _path_exists(path):
        return path
    marker = ".local"
    if marker not in path.parts:
        return path
    marker_index = path.parts.index(marker)
    candidate = repo_root.joinpath(*path.parts[marker_index:])
    return candidate if _path_exists(candidate) else path


def _load_yaml_without_pyyaml(path: Path):
    return repo_load_yaml_without_pyyaml(path)


# ============================================================================
# Operator Tool Interface Contract — ADR 0343
# ============================================================================

import json as _json
import sys as _sys
from pathlib import Path as _Path
from typing import Any as _Any, Optional as _Optional

# ---- Auth loading -----------------------------------------------------------

_PROXMOX_AUTH_REQUIRED_KEYS = {"api_url", "authorization_header"}
_COOLIFY_AUTH_REQUIRED_KEYS = {"url", "token"}


def load_proxmox_auth(auth_file) -> dict:
    """
    Load a Proxmox API token JSON file (schema from proxmox_security role).
    Required keys: api_url, authorization_header.
    Raises FileNotFoundError or ValueError on bad input.
    Raises SystemExit(1) with a human-readable error message.
    """
    path = _Path(auth_file).expanduser()
    if not path.exists():
        _sys.stderr.write(f"ERROR: Proxmox auth file not found: {auth_file}\n")
        raise SystemExit(1)
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _sys.stderr.write(f"ERROR: Cannot parse auth file {auth_file}: {exc}\n")
        raise SystemExit(1)
    missing = _PROXMOX_AUTH_REQUIRED_KEYS - set(data)
    if missing:
        _sys.stderr.write(
            f"ERROR: Auth file '{auth_file}' missing required keys: {', '.join(sorted(missing))}\n"
        )
        raise SystemExit(1)
    return data


def load_operator_auth(auth_file) -> dict:
    """
    Generic operator auth loader. Tries Proxmox schema first, then Coolify schema.
    Returns the dict if any known schema matches.
    Use load_proxmox_auth() or load_coolify_auth() for schema-specific loading.
    """
    path = _Path(auth_file).expanduser()
    if not path.exists():
        _sys.stderr.write(f"ERROR: Auth file not found: {auth_file}\n")
        raise SystemExit(1)
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _sys.stderr.write(f"ERROR: Cannot parse auth file {auth_file}: {exc}\n")
        raise SystemExit(1)
    return data


# ---- JSON stdout output helpers (ADR 0343 exit code contract) ---------------

def tool_output(status: str, **fields) -> None:
    """Write a JSON object to stdout with a 'status' key. All kwargs are included."""
    obj = {"status": status}
    obj.update(fields)
    print(_json.dumps(obj, indent=2))


def tool_exit_noop(**fields) -> None:
    """
    Write {"status": "no_op", ...} to stdout and raise SystemExit(2).
    Use when the operation is already in the desired state.
    """
    tool_output("no_op", **fields)
    raise SystemExit(2)


def tool_exit_error(message: str, **fields) -> None:
    """
    Write error message to stderr and raise SystemExit(1).
    Optionally write JSON with status=error to stdout if fields provided.
    """
    _sys.stderr.write(f"ERROR: {message}\n")
    if fields:
        tool_output("error", detail=message, **fields)
    raise SystemExit(1)


# ---- Topology loading (ADR 0344 snapshot format) ---------------------------

def load_topology_snapshot(snapshot_path, env: str) -> dict:
    """
    Load per-environment topology from a JSON snapshot file (ADR 0344).
    Falls back to an empty dict if the file does not exist (allows
    pure-CLI operation without a snapshot).

    snapshot_path: path to scripts/topology-snapshot.json
    env: environment key e.g. 'prod', 'staging', 'dev'
    """
    path = _Path(snapshot_path).expanduser()
    if not path.exists():
        return {}
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _sys.stderr.write(f"WARNING: Cannot parse topology snapshot {snapshot_path}: {exc}\n")
        return {}
    environments = data.get("environments", {})
    if env not in environments:
        _sys.stderr.write(
            f"WARNING: Environment '{env}' not in snapshot {snapshot_path}. "
            f"Available: {', '.join(sorted(environments))}\n"
        )
        return {}
    return environments[env]


# ---- Guest exec via Proxmox QAPI (ADR 0342) --------------------------------

def proxmox_guest_exec(client, vmid: int, command, timeout: int = 60):
    """
    Execute a command inside a VM via the Proxmox QEMU guest agent.
    Thin wrapper around ProxmoxClient.guest_exec for use in application tools.

    client: a ProxmoxClient instance (from proxmox_tool.py or equivalent)
    vmid: integer VMID of the target VM
    command: list of strings forming the command
    timeout: seconds to wait for the command to finish

    Returns (exit_code: int, stdout: str, stderr: str)
    """
    return client.guest_exec(int(vmid), list(command), timeout=int(timeout))
