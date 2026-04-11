#!/usr/bin/env python3
"""vm_snapshot_tool.py — Create, list, and restore Proxmox VM snapshots.

QUICKSTART FOR LLMs
-------------------
Use this tool BEFORE any risky mutation on a VM:
  - disk resize → create snapshot first
  - config change → create snapshot first
  - playbook run that touches a VM → auto-snapshot first

Snapshots are live (no VM downtime). They use INTENT locks (not EXCLUSIVE)
because no VM state changes are required. Rollback is destructive and requires
the VM to be stopped; the tool will warn you and tell you how to stop it.

USAGE EXAMPLES
--------------
  # Create a snapshot before a risky operation (auto-named, recommended)
  python3 scripts/vm_snapshot_tool.py auto-snapshot --vmid 120

  # Create a named snapshot with a description
  python3 scripts/vm_snapshot_tool.py create --vmid 120 \
      --name pre-resize-20260401 --description "before disk resize"

  # List all snapshots on a VM
  python3 scripts/vm_snapshot_tool.py list --vmid 120

  # Delete a snapshot (--force required for safety)
  python3 scripts/vm_snapshot_tool.py delete --vmid 120 \
      --name pre-resize-20260401 --force

  # Rollback to a snapshot (VM must be stopped; tool will check)
  python3 scripts/vm_snapshot_tool.py rollback --vmid 120 \
      --name pre-resize-20260401 --force

LOCK RESOURCE PATHS (ADR 0153)
-------------------------------
  vm:{vmid}   — INTENT lock acquired before create/delete.
                EXCLUSIVE lock acquired before rollback (destructive).

RECEIPT OUTPUT
--------------
  receipts/vm-snapshots/{vmid}-{snapname}-{timestamp}.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone
    UTC = timezone.utc  # type: ignore[assignment]
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo bootstrap
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.locking import LockType, ResourceLockRegistry

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "all.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
CONTROLLER_SECRETS_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
RECEIPTS_DIR = REPO_ROOT / "receipts" / "vm-snapshots"

DEFAULT_HOLDER = "agent:vm-snapshot-tool"
LOCK_TTL_SECONDS = 300  # 5 min — more than enough for a snapshot


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------


def _yaml_scalar(path: Path, key: str, default: str = "") -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+?)\s*$", flags=re.MULTILINE)
    m = pattern.search(path.read_text(encoding="utf-8"))
    return m.group(1).strip().strip("\"'") if m else default


def _bootstrap_private_key() -> Path:
    payload = json.loads(CONTROLLER_SECRETS_PATH.read_text(encoding="utf-8"))
    return Path(payload["secrets"]["bootstrap_ssh_private_key"]["path"])


def _proxmox_host() -> str:
    env = os.environ.get("LV3_PROXMOX_HOST_ADDR", "").strip()
    if env:
        return env
    ts = _yaml_scalar(HOST_VARS_PATH, "management_tailscale_ipv4")
    return ts or _yaml_scalar(HOST_VARS_PATH, "management_ipv4", "65.108.75.123")


def _jump_user() -> str:
    return _yaml_scalar(GROUP_VARS_PATH, "proxmox_host_admin_user", "ops")


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# SSH to Proxmox host
# ---------------------------------------------------------------------------


def _ssh_to_host(remote_script: str, *, timeout: int = 120) -> subprocess.CompletedProcess:
    key = str(_bootstrap_private_key())
    user = _jump_user()
    host = _proxmox_host()
    cmd = [
        "ssh",
        "-i",
        key,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/dev/null",
        f"{user}@{host}",
        remote_script,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)


def _require_ok(result: subprocess.CompletedProcess, label: str) -> None:
    if result.returncode != 0:
        msg = f"{label} failed (exit {result.returncode})"
        if result.stdout.strip():
            msg += f"\nstdout: {result.stdout.strip()}"
        if result.stderr.strip():
            msg += f"\nstderr: {result.stderr.strip()}"
        raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def load_vm_catalog() -> list[dict[str, Any]]:
    """Parse proxmox_guests list from host_vars/proxmox_florin.yml."""
    text = HOST_VARS_PATH.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import]

        data = yaml.safe_load(text)
        return data.get("proxmox_guests", [])
    except ImportError:
        pass
    # Fallback: crude regex
    vms: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- vmid:"):
            if current:
                vms.append(current)
            current = {"vmid": int(stripped.split(":")[1].strip())}
        elif current is not None:
            for field in ("name", "role", "ipv4"):
                if stripped.startswith(f"{field}:"):
                    current[field] = stripped.split(":", 1)[1].strip()
            if stripped.startswith("disk_gb:"):
                current["disk_gb"] = int(stripped.split(":")[1].strip())
            if stripped.startswith("memory_mb:"):
                current["memory_mb"] = int(stripped.split(":")[1].strip())
    if current:
        vms.append(current)
    return vms


def get_vm(vmid: int) -> dict[str, Any]:
    for vm in load_vm_catalog():
        if vm.get("vmid") == vmid:
            return vm
    raise SystemExit(f"vmid {vmid} not found in inventory. Run list-vms to see known VMs.")


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------


def _build_registry() -> ResourceLockRegistry:
    return ResourceLockRegistry(repo_root=REPO_ROOT)


def _acquire_lock(vmid: int, holder: str, lock_type: LockType = LockType.INTENT) -> str:
    registry = _build_registry()
    entry = registry.acquire(
        resource_path=f"vm:{vmid}",
        lock_type=lock_type,
        holder=holder,
        context_id="vm-snapshot",
        ttl_seconds=LOCK_TTL_SECONDS,
        wait_seconds=0,
    )
    return entry.lock_id


def _release_lock(vmid: int, holder: str) -> int:
    return _build_registry().release(resource_path=f"vm:{vmid}", holder=holder)


# ---------------------------------------------------------------------------
# Receipt writing
# ---------------------------------------------------------------------------


def _write_receipt(vmid: int, snapname: str, payload: dict[str, Any]) -> Path:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    fname = f"{vmid}-{snapname}-{ts}.json"
    path = RECEIPTS_DIR / fname
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Snapshot parsers
# ---------------------------------------------------------------------------


def _parse_listsnapshot(output: str) -> list[dict[str, Any]]:
    """Parse `qm listsnapshot` tab-separated output into a list of dicts.

    Example line:
        `->  current                      now               You are here!`
        `    pre-resize-20260401          2026-04-01 10:00  before disk resize`
    """
    snapshots: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        # Strip leading tree characters (-> and spaces)
        clean = re.sub(r"^[\s\->|]+", "", line)
        parts = clean.split(None, 3)
        if not parts:
            continue
        name = parts[0]
        # Skip the sentinel "current" pseudo-snapshot
        if name.lower() == "current":
            continue
        is_current = line.strip().startswith("->") or "(current)" in line.lower()
        snap: dict[str, Any] = {
            "name": name,
            "time": parts[1] if len(parts) > 1 else "",
            "description": parts[3].strip() if len(parts) > 3 else (parts[2].strip() if len(parts) > 2 else ""),
            "is_current": is_current,
        }
        # If "time" looks like part of a date-time pair, join with next token
        if (
            len(parts) >= 3
            and re.match(r"^\d{4}-\d{2}-\d{2}$", parts[1])
            and re.match(r"^\d{2}:\d{2}:\d{2}$", parts[2])
        ):
            snap["time"] = f"{parts[1]} {parts[2]}"
            snap["description"] = parts[3].strip() if len(parts) > 3 else ""
        snapshots.append(snap)
    return snapshots


# ---------------------------------------------------------------------------
# VM status helper
# ---------------------------------------------------------------------------


def _vm_status(vmid: int) -> str:
    """Return 'running', 'stopped', or 'unknown'."""
    result = _ssh_to_host(f"sudo qm status {vmid}", timeout=30)
    if result.returncode != 0:
        return "unknown"
    m = re.search(r"status:\s*(\S+)", result.stdout)
    return m.group(1).lower() if m else "unknown"


# ---------------------------------------------------------------------------
# sub-command: list
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    """List all snapshots for a VM.

    Output: {vmid, name, snapshots: [{name, time, description, is_current}]}
    """
    vm = get_vm(args.vmid)
    result = _ssh_to_host(f"sudo qm listsnapshot {args.vmid}", timeout=30)
    _require_ok(result, f"qm listsnapshot {args.vmid}")

    snapshots = _parse_listsnapshot(result.stdout)
    print(
        json.dumps(
            {
                "vmid": args.vmid,
                "name": vm.get("name", ""),
                "snapshots": snapshots,
                "count": len(snapshots),
            },
            indent=2,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# sub-command: create
# ---------------------------------------------------------------------------


def cmd_create(args: argparse.Namespace) -> int:
    """Create a named snapshot. Acquires INTENT lock.

    Output: {status, vmid, snapshot_name, timestamp, receipt_path}
    """
    vm = get_vm(args.vmid)
    snapname: str = args.name
    description: str = args.description or f"snapshot created by vm_snapshot_tool at {_now_utc()}"

    # Validate snapshot name: alphanumeric + hyphens, max 40 chars
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-_]{0,39}$", snapname):
        raise SystemExit(
            f"Invalid snapshot name '{snapname}'. Use alphanumeric + hyphens/underscores, "
            f"start with alphanumeric, max 40 chars."
        )

    print(f"[create] Acquiring INTENT lock on vm:{args.vmid} ...", file=sys.stderr)
    lock_id = _acquire_lock(args.vmid, DEFAULT_HOLDER, LockType.INTENT)
    try:
        print(f"[create] Creating snapshot '{snapname}' on vm {args.vmid} ({vm.get('name', '')}) ...", file=sys.stderr)
        # Escape description to avoid shell injection
        safe_desc = description.replace('"', '\\"')
        result = _ssh_to_host(
            f'sudo qm snapshot {args.vmid} {snapname} --description "{safe_desc}"',
            timeout=120,
        )
        _require_ok(result, f"qm snapshot {args.vmid} {snapname}")

        ts = _now_utc()
        receipt_payload = {
            "action": "create",
            "vmid": args.vmid,
            "vm_name": vm.get("name", ""),
            "snapshot_name": snapname,
            "description": description,
            "timestamp": ts,
            "lock_id": lock_id,
            "stdout": result.stdout.strip(),
        }
        receipt_path = _write_receipt(args.vmid, snapname, receipt_payload)

        result_doc = {
            "status": "created",
            "vmid": args.vmid,
            "vm_name": vm.get("name", ""),
            "snapshot_name": snapname,
            "description": description,
            "timestamp": ts,
            "receipt_path": str(receipt_path),
        }
        print(json.dumps(result_doc, indent=2))
        return 0
    finally:
        _release_lock(args.vmid, DEFAULT_HOLDER)


# ---------------------------------------------------------------------------
# sub-command: auto-snapshot
# ---------------------------------------------------------------------------


def cmd_auto_snapshot(args: argparse.Namespace) -> int:
    """Create a snapshot with an auto-generated name: {prefix}-{YYYYMMDDTHHMMSS}.

    This is the recommended pre-operation snapshot for LLMs. Just call:
        python3 scripts/vm_snapshot_tool.py auto-snapshot --vmid 120

    Output: {status, vmid, snapshot_name, timestamp, receipt_path}
    """
    prefix = (args.prefix or "pre-apply").replace(" ", "-")
    ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    auto_name = f"{prefix}-{ts_compact}"
    # Proxmox snapshot names max ~40 chars; truncate prefix if needed
    if len(auto_name) > 40:
        max_prefix = 40 - len(ts_compact) - 1
        prefix = prefix[:max_prefix]
        auto_name = f"{prefix}-{ts_compact}"

    # Delegate to create logic
    args.name = auto_name
    if not hasattr(args, "description") or not args.description:
        args.description = f"auto-snapshot before operation (prefix={args.prefix or 'pre-apply'})"
    return cmd_create(args)


# ---------------------------------------------------------------------------
# sub-command: delete
# ---------------------------------------------------------------------------


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a named snapshot. Requires --force for safety. Acquires INTENT lock.

    Output: {status, vmid, snapshot_name, timestamp}
    """
    if not args.force:
        raise SystemExit(f"Deleting snapshot '{args.name}' on vm {args.vmid} is destructive. Pass --force to confirm.")

    vm = get_vm(args.vmid)

    print(f"[delete] Acquiring INTENT lock on vm:{args.vmid} ...", file=sys.stderr)
    lock_id = _acquire_lock(args.vmid, DEFAULT_HOLDER, LockType.INTENT)
    try:
        print(f"[delete] Deleting snapshot '{args.name}' on vm {args.vmid} ({vm.get('name', '')}) ...", file=sys.stderr)
        result = _ssh_to_host(
            f"sudo qm delsnapshot {args.vmid} {args.name}",
            timeout=120,
        )
        _require_ok(result, f"qm delsnapshot {args.vmid} {args.name}")

        ts = _now_utc()
        result_doc = {
            "status": "deleted",
            "vmid": args.vmid,
            "vm_name": vm.get("name", ""),
            "snapshot_name": args.name,
            "timestamp": ts,
            "lock_id": lock_id,
        }
        print(json.dumps(result_doc, indent=2))
        return 0
    finally:
        _release_lock(args.vmid, DEFAULT_HOLDER)


# ---------------------------------------------------------------------------
# sub-command: rollback
# ---------------------------------------------------------------------------


def cmd_rollback(args: argparse.Namespace) -> int:
    """Roll back a VM to a named snapshot.

    IMPORTANT: The VM must be stopped before rollback. This tool checks first
    and refuses to proceed if it is running (to avoid data corruption). If the
    VM is running, stop it with:
        ssh <proxmox_host> sudo qm stop <vmid>
    Then retry the rollback.

    Requires --force flag. Acquires EXCLUSIVE lock (destructive operation).

    Output: {status, vmid, snapshot_name, vm_was_status, timestamp}
    """
    if not args.force:
        raise SystemExit(
            f"Rolling back vm {args.vmid} to snapshot '{args.name}' is destructive "
            f"and will discard all state since the snapshot. Pass --force to confirm."
        )

    vm = get_vm(args.vmid)

    # Check VM status before acquiring lock
    print(f"[rollback] Checking vm {args.vmid} status ...", file=sys.stderr)
    vm_status = _vm_status(args.vmid)
    if vm_status == "running":
        proxmox_host = _proxmox_host()
        user = _jump_user()
        raise SystemExit(
            f"vm {args.vmid} ({vm.get('name', '')}) is currently RUNNING. "
            f"Rollback requires the VM to be stopped first.\n"
            f"  Stop command: ssh -i <key> {user}@{proxmox_host} 'sudo qm stop {args.vmid}'\n"
            f"  Then retry: python3 scripts/vm_snapshot_tool.py rollback "
            f"--vmid {args.vmid} --name {args.name} --force"
        )

    print(f"[rollback] Acquiring EXCLUSIVE lock on vm:{args.vmid} ...", file=sys.stderr)
    lock_id = _acquire_lock(args.vmid, DEFAULT_HOLDER, LockType.EXCLUSIVE)
    try:
        print(
            f"[rollback] Rolling back vm {args.vmid} ({vm.get('name', '')}) to '{args.name}' ...",
            file=sys.stderr,
        )
        result = _ssh_to_host(
            f"sudo qm rollback {args.vmid} {args.name}",
            timeout=180,
        )
        _require_ok(result, f"qm rollback {args.vmid} {args.name}")

        ts = _now_utc()
        receipt_payload = {
            "action": "rollback",
            "vmid": args.vmid,
            "vm_name": vm.get("name", ""),
            "snapshot_name": args.name,
            "vm_was_status": vm_status,
            "timestamp": ts,
            "lock_id": lock_id,
            "stdout": result.stdout.strip(),
        }
        receipt_path = _write_receipt(args.vmid, args.name, receipt_payload)

        result_doc = {
            "status": "rolled_back",
            "vmid": args.vmid,
            "vm_name": vm.get("name", ""),
            "snapshot_name": args.name,
            "vm_was_status": vm_status,
            "timestamp": ts,
            "receipt_path": str(receipt_path),
        }
        print(json.dumps(result_doc, indent=2))
        return 0
    finally:
        _release_lock(args.vmid, DEFAULT_HOLDER)


# ---------------------------------------------------------------------------
# sub-command: list-vms  (convenience: show all VMs from inventory)
# ---------------------------------------------------------------------------


def cmd_list_vms(args: argparse.Namespace) -> int:
    """List all VMs known to inventory (no SSH required).

    Output: {vms: [{vmid, name, role, ipv4, disk_gb, memory_mb}]}
    """
    vms = load_vm_catalog()
    rows = [
        {
            "vmid": vm.get("vmid"),
            "name": vm.get("name", ""),
            "role": vm.get("role", ""),
            "ipv4": vm.get("ipv4", ""),
            "disk_gb": vm.get("disk_gb", "?"),
            "memory_mb": vm.get("memory_mb", "?"),
        }
        for vm in vms
    ]
    print(json.dumps({"vms": rows}, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, list, and restore Proxmox VM snapshots (ADR 0153 lock-aware).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List snapshots for a VM.")
    p_list.add_argument("--vmid", type=int, required=True, help="Proxmox VMID.")

    # create
    p_create = sub.add_parser("create", help="Create a named snapshot.")
    p_create.add_argument("--vmid", type=int, required=True, help="Proxmox VMID.")
    p_create.add_argument("--name", required=True, help="Snapshot name (alphanumeric + hyphens, max 40 chars).")
    p_create.add_argument("--description", default="", help="Human-readable description stored with the snapshot.")

    # auto-snapshot
    p_auto = sub.add_parser(
        "auto-snapshot",
        help="Create a snapshot with an auto-generated name: {prefix}-{YYYYMMDDTHHMMSS}. Use before risky ops.",
    )
    p_auto.add_argument("--vmid", type=int, required=True, help="Proxmox VMID.")
    p_auto.add_argument("--prefix", default="pre-apply", help="Name prefix (default: pre-apply).")
    p_auto.add_argument("--description", default="", help="Optional description.")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a snapshot (--force required).")
    p_delete.add_argument("--vmid", type=int, required=True, help="Proxmox VMID.")
    p_delete.add_argument("--name", required=True, help="Snapshot name to delete.")
    p_delete.add_argument("--force", action="store_true", help="Required safety flag.")

    # rollback
    p_rollback = sub.add_parser("rollback", help="Roll back VM to a snapshot (--force required; VM must be stopped).")
    p_rollback.add_argument("--vmid", type=int, required=True, help="Proxmox VMID.")
    p_rollback.add_argument("--name", required=True, help="Snapshot name to roll back to.")
    p_rollback.add_argument(
        "--force", action="store_true", help="Required safety flag (confirms destructive rollback)."
    )

    # list-vms
    sub.add_parser("list-vms", help="List all VMs from inventory (no SSH needed).")

    return parser


# ---------------------------------------------------------------------------
# Dispatch + main
# ---------------------------------------------------------------------------

_COMMANDS = {
    "list": cmd_list,
    "create": cmd_create,
    "auto-snapshot": cmd_auto_snapshot,
    "delete": cmd_delete,
    "rollback": cmd_rollback,
    "list-vms": cmd_list_vms,
}


def main() -> int:
    args = build_parser().parse_args()
    try:
        handler = _COMMANDS[args.command]
        return handler(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
