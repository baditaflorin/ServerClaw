#!/usr/bin/env python3
"""vm_disk_resize_tool.py — Safe, lock-aware VM disk + LVM resize for this platform.

QUICKSTART FOR LLMs
-------------------
This tool is the canonical way to grow a VM's disk when a filesystem is running low.
It handles the full pipeline:
  1. Lock check   — refuses to proceed if another agent holds an exclusive lock on the VM.
  2. Lock acquire — takes an exclusive lock before any mutation.
  3. Proxmox resize — runs `qm resize <vmid> scsi0 +Ng` on the Proxmox host via SSH.
  4. Guest expand  — SSHes into the guest via the Proxmox jump host and:
                     growpart → pvresize → lvextend → resize2fs / xfs_growfs.
  5. Inventory update — optionally patches disk_gb in host_vars so the repo stays
                        in sync with reality.
  6. Lock release  — always released (even on error, via finally).
  7. Receipt       — JSON summary written to receipts/vm-disk-resize/.

USAGE EXAMPLES
--------------
  # List all managed VMs with current disk_gb and lock status (no SSH needed)
  python3 scripts/vm_disk_resize_tool.py list

  # Inspect the live disk/LVM layout inside a guest (read-only SSH)
  python3 scripts/vm_disk_resize_tool.py inspect --vmid 120

  # Dry-run: show exactly what would change (default, no mutations)
  python3 scripts/vm_disk_resize_tool.py resize --vmid 120 --add-gb 32

  # Actually apply: grow vm:120 by 32 GB and update inventory
  python3 scripts/vm_disk_resize_tool.py resize --vmid 120 --add-gb 32 --apply --update-inventory

  # Set an absolute target size (must be larger than current)
  python3 scripts/vm_disk_resize_tool.py resize --vmid 120 --target-gb 160 --apply

  # Force-release a stale lock held by a dead agent, then resize
  python3 scripts/vm_disk_resize_tool.py release-lock --vmid 120
  python3 scripts/vm_disk_resize_tool.py resize --vmid 120 --add-gb 32 --apply

LOCK RESOURCE PATHS (ADR 0153)
-------------------------------
  vm:{vmid}              — exclusive lock acquired before any resize mutation.
  vm:{vmid}/service:*    — child locks (inspected; not acquired by this tool).

The tool will EXIT with a non-zero code if an active exclusive lock exists on the
target VM, unless you use `release-lock` first (for dead agents) or set
--force-locked (skips the check — use only when you are certain the holder is gone).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo bootstrap — same pattern as resource_lock_tool.py
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.locking import LockType, ResourceLockRegistry

# ---------------------------------------------------------------------------
# Paths (mirrors fixture_manager.py conventions)
# ---------------------------------------------------------------------------

GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "all.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
CONTROLLER_SECRETS_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
RECEIPTS_DIR = REPO_ROOT / "receipts" / "vm-disk-resize"

DEFAULT_HOLDER = "agent:vm-disk-resize-tool"
LOCK_TTL_SECONDS = 900  # 15 min — plenty for any resize operation


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _yaml_scalar(path: Path, key: str, default: str = "") -> str:
    """Extract a simple scalar from YAML without a full YAML dependency."""
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+?)\s*$", flags=re.MULTILINE)
    match = pattern.search(path.read_text(encoding="utf-8"))
    if not match:
        return default
    return match.group(1).strip().strip("\"'")


def _bootstrap_private_key() -> Path:
    payload = _load_json(CONTROLLER_SECRETS_PATH)
    return Path(payload["secrets"]["bootstrap_ssh_private_key"]["path"])


def _proxmox_host() -> str:
    """Return the Proxmox host address (env override → tailscale → management IP)."""
    env = os.environ.get("LV3_PROXMOX_HOST_ADDR", "").strip()
    if env:
        return env
    ts = _yaml_scalar(HOST_VARS_PATH, "management_tailscale_ipv4")
    if ts:
        return ts
    return _yaml_scalar(HOST_VARS_PATH, "management_ipv4", "65.108.75.123")


def _jump_user() -> str:
    return _yaml_scalar(GROUP_VARS_PATH, "proxmox_host_admin_user", "ops")


def _guest_user() -> str:
    return _yaml_scalar(GROUP_VARS_PATH, "proxmox_guest_ci_user", "ops")


# ---------------------------------------------------------------------------
# Inventory: load all managed VMs from host_vars
# ---------------------------------------------------------------------------


def load_vm_catalog() -> list[dict[str, Any]]:
    """Parse the proxmox_vms list from inventory/host_vars/proxmox_florin.yml."""
    text = HOST_VARS_PATH.read_text(encoding="utf-8")
    # Find the proxmox_vms block and extract each VM entry as a mini-dict.
    # We do simple regex parsing — avoids a hard PyYAML dep in a CLI tool.
    try:
        import yaml  # type: ignore[import]

        data = yaml.safe_load(text)
        return data.get("proxmox_vms", [])
    except ImportError:
        pass
    # Fallback: crude regex to extract vmid/name/disk_gb/ipv4 lines
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
    catalog = load_vm_catalog()
    for vm in catalog:
        if vm.get("vmid") == vmid:
            return vm
    raise SystemExit(f"vmid {vmid} not found in inventory. Run `list` to see known VMs.")


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------


def _build_registry() -> ResourceLockRegistry:
    return ResourceLockRegistry(repo_root=REPO_ROOT)


def _lock_status(vmid: int) -> dict[str, Any]:
    """Return lock info dict for vm:{vmid}. Keys: locked (bool), holder, expires_at."""
    registry = _build_registry()
    locks = registry.read_all()
    resource = f"vm:{vmid}"
    for lock in locks:
        if lock.resource_path == resource and lock.lock_type == LockType.EXCLUSIVE:
            return {
                "locked": True,
                "holder": lock.holder,
                "lock_id": lock.lock_id,
                "expires_at": lock.expires_at,
                "context_id": lock.context_id,
            }
    return {"locked": False}


def _acquire_lock(vmid: int, holder: str) -> str:
    registry = _build_registry()
    entry = registry.acquire(
        resource_path=f"vm:{vmid}",
        lock_type=LockType.EXCLUSIVE,
        holder=holder,
        context_id="vm-disk-resize",
        ttl_seconds=LOCK_TTL_SECONDS,
        wait_seconds=0,
    )
    return entry.lock_id


def _release_lock(vmid: int, holder: str) -> int:
    registry = _build_registry()
    return registry.release(resource_path=f"vm:{vmid}", holder=holder)


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------


def _ssh_to_host(remote_script: str, *, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a shell script on the Proxmox host itself."""
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


def _ssh_to_guest(guest_ip: str, remote_script: str, *, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a shell script inside a guest VM, jumping via the Proxmox host."""
    key = str(_bootstrap_private_key())
    jump_user = _jump_user()
    jump_host = _proxmox_host()
    guest_user = _guest_user()
    proxy = (
        f"ssh -i {key} -o IdentitiesOnly=yes -o BatchMode=yes "
        f"-o ConnectTimeout=10 -o StrictHostKeyChecking=no "
        f"-o UserKnownHostsFile=/dev/null "
        f"{jump_user}@{jump_host} -W %h:%p"
    )
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
        "-o",
        f"ProxyCommand={proxy}",
        f"{guest_user}@{guest_ip}",
        remote_script,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)


def _require_ok(result: subprocess.CompletedProcess, label: str) -> None:
    if result.returncode != 0:
        print(f"[ERROR] {label} failed (exit {result.returncode})", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


# ---------------------------------------------------------------------------
# Guest LVM inspection script
# ---------------------------------------------------------------------------

_INSPECT_SCRIPT = r"""#!/bin/bash
set -uo pipefail
echo '{"lsblk":' ; lsblk -J -b -o NAME,TYPE,FSTYPE,MOUNTPOINT,SIZE,PKNAME 2>/dev/null || echo 'null'
echo ',"df":' ; df -B1 --output=source,fstype,size,used,avail,pcent,target 2>/dev/null | python3 -c "
import sys, json
lines = sys.stdin.read().strip().splitlines()
hdr = lines[0].split()
rows = []
for line in lines[1:]:
    parts = line.split()
    if len(parts) >= len(hdr):
        rows.append(dict(zip(hdr, parts)))
print(json.dumps(rows))
"
echo ',"pvs":' ; sudo pvs --reportformat json -o pv_name,vg_name,pv_size,pv_free 2>/dev/null | python3 -c "
import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('report',[{}])[0].get('pv',[])))
" 2>/dev/null || echo '[]'
echo ',"vgs":' ; sudo vgs --reportformat json -o vg_name,vg_size,vg_free 2>/dev/null | python3 -c "
import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('report',[{}])[0].get('vg',[])))
" 2>/dev/null || echo '[]'
echo ',"lvs":' ; sudo lvs --reportformat json -o lv_name,vg_name,lv_path,lv_size,data_percent 2>/dev/null | python3 -c "
import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('report',[{}])[0].get('lv',[])))
" 2>/dev/null || echo '[]'
echo '}'
"""

# ---------------------------------------------------------------------------
# Guest LVM expansion script
# Auto-detects: disk → LVM partition → PV → VG → LVs → filesystems
# ---------------------------------------------------------------------------

_EXPAND_SCRIPT = r"""#!/bin/bash
set -euo pipefail

# Full paths so sudo doesn't lose /usr/sbin
GROWPART=$(command -v growpart 2>/dev/null || echo /usr/bin/growpart)
PVRESIZE=/usr/sbin/pvresize
VGS_BIN=/usr/sbin/vgs
LVS_BIN=/usr/sbin/lvs
LVEXTEND=/usr/sbin/lvextend
BLKID=/usr/sbin/blkid
FINDMNT=$(command -v findmnt 2>/dev/null || echo /usr/bin/findmnt)
RESIZE2FS=$(command -v resize2fs 2>/dev/null || echo /usr/sbin/resize2fs)
XFS_GROWFS=$(command -v xfs_growfs 2>/dev/null || echo /usr/sbin/xfs_growfs)

echo "==> Detecting primary disk ..."
DISK=$(lsblk -dpn -o NAME,TYPE | awk '$2=="disk"{print $1}' | grep -v loop | head -1)
echo "    Disk: $DISK (current kernel size: $(lsblk -dbn -o SIZE "$DISK") bytes)"

echo "==> Checking for LVM PVs ..."
HAS_LVM=0
if command -v pvs &>/dev/null || [ -x "$PVRESIZE" ]; then
  PV_LIST=$(sudo "$PVRESIZE" --test 2>/dev/null && sudo /usr/sbin/pvs --noheadings -o pv_name 2>/dev/null | tr -d ' ' || true)
  [ -n "$PV_LIST" ] && HAS_LVM=1
fi
# Also check lsblk FSTYPE (needs sudo to read partition metadata reliably)
LVM_PART=$(sudo lsblk -pn -o NAME,FSTYPE "$DISK" 2>/dev/null | awk '$2=="LVM2_member"{print $1}' | head -1 || true)
[ -n "$LVM_PART" ] && HAS_LVM=1

if [ "$HAS_LVM" -eq 0 ]; then
  # ---------------------------------------------------------------
  # Simple layout: plain partition → ext4/xfs directly (no LVM)
  # ---------------------------------------------------------------
  echo "    No LVM detected — using direct growpart + filesystem resize."

  # Find the largest numbered partition (usually root)
  ROOT_PART=$(sudo lsblk -pn -o NAME,MOUNTPOINT "$DISK" 2>/dev/null | awk '$2=="/"{print $1}' | head -1)
  if [ -z "$ROOT_PART" ]; then
    # fallback: largest partition by size
    ROOT_PART=$(sudo lsblk -pbn -o NAME,TYPE,SIZE "$DISK" | awk '$2=="part"{print $3,$1}' | sort -rn | head -1 | awk '{print $2}')
  fi
  PART_NUM=$(echo "$ROOT_PART" | grep -oE '[0-9]+$')
  echo "    Root partition: $ROOT_PART (part $PART_NUM)"

  echo "==> growpart $DISK $PART_NUM ..."
  sudo "$GROWPART" "$DISK" "$PART_NUM" || echo "    (already at max — continuing)"

  FSTYPE=$(sudo "$BLKID" -o value -s TYPE "$ROOT_PART" 2>/dev/null || echo "ext4")
  echo "    Filesystem: $FSTYPE"
  case "$FSTYPE" in
    ext2|ext3|ext4)
      echo "==> resize2fs $ROOT_PART ..."
      sudo "$RESIZE2FS" "$ROOT_PART"
      ;;
    xfs)
      MOUNT=$(sudo "$FINDMNT" -n -o TARGET --source "$ROOT_PART" 2>/dev/null || echo "/")
      echo "==> xfs_growfs $MOUNT ..."
      sudo "$XFS_GROWFS" "$MOUNT"
      ;;
    *)
      echo "WARNING: Unknown filesystem '$FSTYPE' — resize manually."
      ;;
  esac

else
  # ---------------------------------------------------------------
  # LVM layout: growpart → pvresize → lvextend → fs resize
  # ---------------------------------------------------------------
  echo "    LVM detected. LVM partition: ${LVM_PART:-whole-disk}"

  if [ -n "$LVM_PART" ]; then
    PART_NUM=$(echo "$LVM_PART" | grep -oE '[0-9]+$' || true)
    if [ -n "$PART_NUM" ]; then
      echo "==> growpart $DISK $PART_NUM ..."
      sudo "$GROWPART" "$DISK" "$PART_NUM" || echo "    (already at max — continuing)"
    fi
    echo "==> pvresize $LVM_PART ..."
    sudo "$PVRESIZE" "$LVM_PART"
  else
    echo "==> pvresize $DISK (whole-disk PV) ..."
    sudo "$PVRESIZE" "$DISK"
  fi

  VG_LIST=$(sudo "$VGS_BIN" --noheadings -o vg_name 2>/dev/null | tr -d ' ')
  for VG in $VG_LIST; do
    FREE=$(sudo "$VGS_BIN" --noheadings --units b -o vg_free "$VG" 2>/dev/null | tr -d ' Bb')
    echo "==> VG $VG — free bytes: ${FREE:-0}"
    [ "${FREE:-0}" -lt 1048576 ] && continue

    LARGEST_LV=$(sudo "$LVS_BIN" --noheadings -o lv_name,lv_size --units b --nosuffix "$VG" 2>/dev/null \
      | awk '{print $2, $1}' | sort -rn | head -1 | awk '{print $2}')
    LV_PATH="/dev/$VG/$LARGEST_LV"
    echo "    lvextend -l +100%FREE $LV_PATH ..."
    sudo "$LVEXTEND" -l +100%FREE "$LV_PATH"

    FSTYPE=$(sudo "$BLKID" -o value -s TYPE "$LV_PATH" 2>/dev/null || echo "unknown")
    case "$FSTYPE" in
      ext2|ext3|ext4) sudo "$RESIZE2FS" "$LV_PATH" ;;
      xfs)
        MOUNT=$(sudo "$FINDMNT" -n -o TARGET --source "$LV_PATH" 2>/dev/null || echo "/")
        sudo "$XFS_GROWFS" "$MOUNT" ;;
      *) echo "WARNING: Unknown fs '$FSTYPE' on $LV_PATH — resize manually." ;;
    esac
  done
fi

echo ""
echo "==> Post-resize disk usage:"
df -h
echo "==> Done."
"""


# ---------------------------------------------------------------------------
# sub-command: list
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    vms = load_vm_catalog()
    registry = _build_registry()
    all_locks = registry.read_all()
    lock_map: dict[str, dict] = {}
    for lock in all_locks:
        if lock.lock_type == LockType.EXCLUSIVE:
            lock_map[lock.resource_path] = {
                "holder": lock.holder,
                "expires_at": lock.expires_at,
            }

    rows = []
    for vm in vms:
        vmid = vm.get("vmid")
        lock_info = lock_map.get(f"vm:{vmid}", {})
        rows.append(
            {
                "vmid": vmid,
                "name": vm.get("name", ""),
                "role": vm.get("role", ""),
                "ipv4": vm.get("ipv4", ""),
                "disk_gb": vm.get("disk_gb", "?"),
                "memory_mb": vm.get("memory_mb", "?"),
                "locked": bool(lock_info),
                "lock_holder": lock_info.get("holder", ""),
                "lock_expires_at": lock_info.get("expires_at", ""),
            }
        )

    print(json.dumps({"vms": rows, "lock_count": len(lock_map)}, indent=2))
    return 0


# ---------------------------------------------------------------------------
# sub-command: inspect
# ---------------------------------------------------------------------------


def cmd_inspect(args: argparse.Namespace) -> int:
    vm = get_vm(args.vmid)
    guest_ip = vm.get("ipv4", "")
    if not guest_ip:
        raise SystemExit(f"vmid {args.vmid} has no ipv4 in inventory.")

    print(f"[inspect] SSHing into {vm['name']} ({guest_ip}) ...", file=sys.stderr)
    result = _ssh_to_guest(guest_ip, _INSPECT_SCRIPT, timeout=30)
    _require_ok(result, "inspect")

    # The script emits one JSON object spread across echo statements.
    # Reassemble by collecting lines between the opening { and closing }.
    raw = result.stdout.strip()
    # Parse the output — the script emits valid JSON fragments.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: just print raw
        print(raw)
        return 0

    print(json.dumps({"vmid": args.vmid, "name": vm["name"], **data}, indent=2))
    return 0


# ---------------------------------------------------------------------------
# sub-command: resize
# ---------------------------------------------------------------------------


def cmd_resize(args: argparse.Namespace) -> int:
    vm = get_vm(args.vmid)
    current_gb: int = vm.get("disk_gb", 0)
    guest_ip: str = vm.get("ipv4", "")
    disk: str = args.disk

    # Compute new size
    if args.add_gb and args.target_gb:
        raise SystemExit("Specify either --add-gb or --target-gb, not both.")
    if args.add_gb:
        new_gb = current_gb + args.add_gb
        delta_gb = args.add_gb
    elif args.target_gb:
        if args.target_gb <= current_gb:
            raise SystemExit(f"--target-gb {args.target_gb} must be larger than current {current_gb} GB.")
        new_gb = args.target_gb
        delta_gb = new_gb - current_gb
    else:
        raise SystemExit("Specify --add-gb or --target-gb.")

    print(
        f"[resize] vm:{args.vmid} ({vm['name']})  {current_gb} GB → {new_gb} GB  (+{delta_gb} GB on {disk})",
        file=sys.stderr,
    )

    # ------------------------------------------------------------------ #
    # Lock check
    # ------------------------------------------------------------------ #
    lock_info = _lock_status(args.vmid)
    if lock_info["locked"] and not args.force_locked:
        raise SystemExit(
            f"vm:{args.vmid} is exclusively locked by '{lock_info['holder']}' "
            f"(expires {lock_info['expires_at']}).\n"
            f"  → If that agent is dead, run:  "
            f"python3 scripts/vm_disk_resize_tool.py release-lock --vmid {args.vmid}\n"
            f"  → Or pass --force-locked to skip this check (dangerous)."
        )

    # ------------------------------------------------------------------ #
    # Dry-run: just show the plan
    # ------------------------------------------------------------------ #
    plan = {
        "vmid": args.vmid,
        "name": vm["name"],
        "disk": disk,
        "current_gb": current_gb,
        "new_gb": new_gb,
        "delta_gb": delta_gb,
        "phases": [
            {
                "phase": 1,
                "where": "proxmox_host",
                "command": f"sudo qm resize {args.vmid} {disk} {new_gb}G",
                "note": "Online resize — no VM downtime required.",
            },
            {
                "phase": 2,
                "where": f"guest {guest_ip}",
                "command": "(auto-detect: growpart → pvresize → lvextend → resize2fs/xfs_growfs)",
                "note": "Expands LVM PV, extends largest LV, resizes filesystem online.",
            },
        ],
        "inventory_update": args.update_inventory,
        "dry_run": not args.apply,
    }

    if not args.apply:
        print(json.dumps({"status": "dry_run", "plan": plan}, indent=2))
        print(
            "\n[dry-run] No changes made. Add --apply to execute.",
            file=sys.stderr,
        )
        return 0

    # ------------------------------------------------------------------ #
    # Acquire lock
    # ------------------------------------------------------------------ #
    holder = args.holder
    lock_id: str | None = None
    try:
        lock_id = _acquire_lock(args.vmid, holder)
        print(f"[lock] Acquired exclusive lock on vm:{args.vmid}  (id={lock_id})", file=sys.stderr)

        # ---------------------------------------------------------------- #
        # Phase 1: Proxmox host — qm resize
        # ---------------------------------------------------------------- #
        print(f"[phase-1] Resizing Proxmox disk: qm resize {args.vmid} {disk} {new_gb}G", file=sys.stderr)
        phase1_cmd = f"sudo qm resize {args.vmid} {disk} {new_gb}G"
        p1 = _ssh_to_host(phase1_cmd, timeout=60)
        _require_ok(p1, "qm resize")
        print(f"[phase-1] OK — Proxmox disk is now {new_gb} GB", file=sys.stderr)

        # ---------------------------------------------------------------- #
        # Phase 2: Guest — LVM expansion
        # ---------------------------------------------------------------- #
        guest_result: subprocess.CompletedProcess | None = None
        if args.skip_guest:
            print("[phase-2] Skipped (--skip-guest)", file=sys.stderr)
        else:
            if not guest_ip:
                print(
                    f"[phase-2] WARNING: vmid {args.vmid} has no ipv4 — skipping guest expansion.",
                    file=sys.stderr,
                )
            else:
                print(f"[phase-2] Expanding LVM inside guest {guest_ip} ...", file=sys.stderr)
                guest_result = _ssh_to_guest(guest_ip, _EXPAND_SCRIPT, timeout=120)
                _require_ok(guest_result, "guest LVM expansion")
                print("[phase-2] OK", file=sys.stderr)
                if guest_result.stdout:
                    print(guest_result.stdout, file=sys.stderr)

        # ---------------------------------------------------------------- #
        # Inventory update
        # ---------------------------------------------------------------- #
        if args.update_inventory:
            _update_inventory_disk_gb(args.vmid, new_gb)
            print(f"[inventory] Updated disk_gb for vmid {args.vmid} to {new_gb}", file=sys.stderr)

        # ---------------------------------------------------------------- #
        # Receipt
        # ---------------------------------------------------------------- #
        receipt = {
            "tool": "vm_disk_resize_tool",
            "timestamp": datetime.now(UTC).isoformat(),
            "vmid": args.vmid,
            "name": vm["name"],
            "disk": disk,
            "before_gb": current_gb,
            "after_gb": new_gb,
            "delta_gb": delta_gb,
            "lock_id": lock_id,
            "holder": holder,
            "inventory_updated": args.update_inventory,
            "guest_expand_stdout": guest_result.stdout if guest_result else None,
        }
        _write_receipt(receipt)

        result_payload = {"status": "success", "receipt": receipt}
        print(json.dumps(result_payload, indent=2))
        return 0

    finally:
        if lock_id is not None:
            released = _release_lock(args.vmid, holder)
            print(f"[lock] Released lock on vm:{args.vmid} ({released} removed)", file=sys.stderr)


# ---------------------------------------------------------------------------
# sub-command: expand-guest
# Run ONLY the guest LVM expansion (phase-2). Use when the Proxmox disk was
# already resized (phase-1 succeeded) but the guest expansion failed.
# ---------------------------------------------------------------------------


def cmd_expand_guest(args: argparse.Namespace) -> int:
    vm = get_vm(args.vmid)
    guest_ip: str = vm.get("ipv4", "")
    if not guest_ip:
        raise SystemExit(f"vmid {args.vmid} has no ipv4 in inventory.")

    lock_info = _lock_status(args.vmid)
    if lock_info["locked"] and not args.force_locked:
        raise SystemExit(
            f"vm:{args.vmid} is locked by '{lock_info['holder']}' (expires {lock_info['expires_at']}).\n"
            f"  → Run release-lock first, or pass --force-locked."
        )

    holder = args.holder
    lock_id = _acquire_lock(args.vmid, holder)
    print(f"[lock] Acquired exclusive lock on vm:{args.vmid} (id={lock_id})", file=sys.stderr)
    try:
        print(f"[expand-guest] SSHing into {vm['name']} ({guest_ip}) ...", file=sys.stderr)
        result = _ssh_to_guest(guest_ip, _EXPAND_SCRIPT, timeout=120)
        _require_ok(result, "guest LVM expansion")
        print(result.stdout, file=sys.stderr)
        print(json.dumps({"status": "success", "vmid": args.vmid, "name": vm["name"]}))
        return 0
    finally:
        released = _release_lock(args.vmid, holder)
        print(f"[lock] Released lock on vm:{args.vmid} ({released} removed)", file=sys.stderr)


# ---------------------------------------------------------------------------
# sub-command: release-lock
# ---------------------------------------------------------------------------


def cmd_release_lock(args: argparse.Namespace) -> int:
    """Force-release any exclusive lock on vm:{vmid}. Use when a holder agent is dead."""
    registry = _build_registry()
    locks = registry.read_all()
    resource = f"vm:{args.vmid}"
    target_locks = [lk for lk in locks if lk.resource_path == resource and lk.lock_type == LockType.EXCLUSIVE]
    if not target_locks:
        print(json.dumps({"status": "nothing_to_release", "resource": resource}))
        return 0

    released_list = []
    for lk in target_locks:
        count = registry.release(lock_id=lk.lock_id)
        released_list.append(
            {
                "lock_id": lk.lock_id,
                "holder": lk.holder,
                "expires_at": lk.expires_at,
                "released": count,
            }
        )
    print(json.dumps({"status": "released", "resource": resource, "locks": released_list}, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Inventory patcher
# ---------------------------------------------------------------------------


def _update_inventory_disk_gb(vmid: int, new_gb: int) -> None:
    """Patch the disk_gb for vmid in proxmox_florin.yml (in-place, minimal diff)."""
    text = HOST_VARS_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # Find the block for this vmid, then update the next disk_gb line after it.
    in_block = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped == f"- vmid: {vmid}":
            in_block = True
        elif in_block and stripped.startswith("- vmid:"):
            in_block = False  # left this VM's block
        if in_block and re.match(r"^\s+disk_gb:\s+\d+", line):
            indent = len(line) - len(line.lstrip())
            line = " " * indent + f"disk_gb: {new_gb}\n"
            in_block = False  # only patch the first occurrence
        new_lines.append(line)
    HOST_VARS_PATH.write_text("".join(new_lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Receipt writer
# ---------------------------------------------------------------------------


def _write_receipt(receipt: dict) -> None:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RECEIPTS_DIR / f"{ts}-vmid-{receipt['vmid']}.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[receipt] Written to {path.relative_to(REPO_ROOT)}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vm_disk_resize_tool.py",
        description=textwrap.dedent("""\
            Safe, lock-aware VM disk + LVM resize tool.

            Subcommands:
              list          List managed VMs with disk sizes and lock status.
              inspect       Inspect live disk/LVM layout inside a guest (read-only).
              resize        Resize a VM disk (Proxmox + guest LVM in one shot).
              release-lock  Force-release a stale exclusive lock on a VM.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # list
    subs.add_parser("list", help="List all managed VMs with disk_gb and lock status.")

    # inspect
    p_inspect = subs.add_parser("inspect", help="Inspect live disk/LVM layout (read-only SSH).")
    p_inspect.add_argument("--vmid", type=int, required=True, help="Proxmox VM ID (e.g. 120).")

    # resize
    p_resize = subs.add_parser("resize", help="Resize disk + expand LVM inside the guest.")
    p_resize.add_argument("--vmid", type=int, required=True, help="Proxmox VM ID.")
    size_group = p_resize.add_mutually_exclusive_group(required=True)
    size_group.add_argument("--add-gb", type=int, metavar="N", help="Add N GB to the current disk size.")
    size_group.add_argument(
        "--target-gb", type=int, metavar="N", help="Set the disk to exactly N GB (must be larger than current)."
    )
    p_resize.add_argument("--disk", default="scsi0", help="Proxmox disk device name (default: scsi0).")
    p_resize.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually perform the resize. Without this flag the command is a dry-run.",
    )
    p_resize.add_argument(
        "--skip-guest",
        action="store_true",
        default=False,
        help="Resize only the Proxmox-side disk; skip growpart/lvextend inside the guest.",
    )
    p_resize.add_argument(
        "--update-inventory",
        action="store_true",
        default=False,
        help="Patch disk_gb in inventory/host_vars/proxmox_florin.yml after a successful resize.",
    )
    p_resize.add_argument(
        "--force-locked",
        action="store_true",
        default=False,
        help="Skip the lock-held check (use only when the existing holder is confirmed dead).",
    )
    p_resize.add_argument(
        "--holder",
        default=DEFAULT_HOLDER,
        help=f"Lock holder identifier (default: {DEFAULT_HOLDER}).",
    )

    # expand-guest
    p_eg = subs.add_parser(
        "expand-guest",
        help="Run only the guest LVM expansion (phase-2). Use when phase-1 already completed.",
    )
    p_eg.add_argument("--vmid", type=int, required=True)
    p_eg.add_argument("--force-locked", action="store_true", default=False)
    p_eg.add_argument("--holder", default=DEFAULT_HOLDER)

    # release-lock
    p_rel = subs.add_parser("release-lock", help="Force-release a stale exclusive lock on a VM.")
    p_rel.add_argument("--vmid", type=int, required=True, help="Proxmox VM ID whose lock to release.")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "list":
            return cmd_list(args)
        if args.command == "inspect":
            return cmd_inspect(args)
        if args.command == "resize":
            return cmd_resize(args)
        if args.command == "expand-guest":
            return cmd_expand_guest(args)
        if args.command == "release-lock":
            return cmd_release_lock(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
