#!/usr/bin/env python3
"""inventory_diff_tool.py — Diff inventory desired state vs. live Proxmox VM state.

QUICKSTART FOR LLMs
-------------------
Run before making changes to detect if the inventory is already out of sync
with what Proxmox actually has. Also use after a live apply to confirm the
inventory reflects reality.

Compares: disk_gb, memory_mb (memory), cores, name, tags.

USAGE EXAMPLES
--------------
  # Diff all VMs (requires SSH to Proxmox host)
  python3 scripts/inventory_diff_tool.py diff

  # Diff a single VM
  python3 scripts/inventory_diff_tool.py diff --vmid 120

  # Quick pass/fail (good for scripting)
  python3 scripts/inventory_diff_tool.py check

  # Update inventory to match live state (dry-run by default)
  python3 scripts/inventory_diff_tool.py sync-inventory --vmid 120
  python3 scripts/inventory_diff_tool.py sync-inventory --vmid 120 --apply

EXIT CODES
----------
  0 — clean (inventory matches live)
  1 — error (SSH failed, file missing)
  2 — drift detected
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from platform.repo import TOPOLOGY_HOST_VARS_PATH
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "all.yml"
CONTROLLER_SECRETS_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"


# ---------------------------------------------------------------------------
# SSH / Proxmox helpers (same pattern as vm_disk_resize_tool.py)
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
    ts = _yaml_scalar(TOPOLOGY_HOST_VARS_PATH, "management_tailscale_ipv4")
    return ts or _yaml_scalar(TOPOLOGY_HOST_VARS_PATH, "management_ipv4", "203.0.113.1")


def _jump_user() -> str:
    return _yaml_scalar(GROUP_VARS_PATH, "proxmox_host_admin_user", "ops")


def _ssh_to_host(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    key = str(_bootstrap_private_key())
    return subprocess.run(
        [
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
            f"{_jump_user()}@{_proxmox_host()}",
            cmd,
        ],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
    )


# ---------------------------------------------------------------------------
# Inventory loader
# ---------------------------------------------------------------------------


def _load_inventory_vms() -> list[dict[str, Any]]:
    try:
        import yaml  # type: ignore[import]

        data = yaml.safe_load(TOPOLOGY_HOST_VARS_PATH.read_text(encoding="utf-8"))
        return data.get("proxmox_vms", [])
    except ImportError:
        pass
    # Fallback regex
    text = TOPOLOGY_HOST_VARS_PATH.read_text(encoding="utf-8")
    vms: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- vmid:"):
            if current:
                vms.append(current)
            current = {"vmid": int(s.split(":")[1].strip())}
        elif current is not None:
            for field in ("name", "role", "ipv4"):
                if s.startswith(f"{field}:"):
                    current[field] = s.split(":", 1)[1].strip()
            for int_field in ("disk_gb", "memory_mb", "cores"):
                if s.startswith(f"{int_field}:"):
                    try:
                        current[int_field] = int(s.split(":")[1].strip())
                    except ValueError:
                        pass
            if s.startswith("tags:") and "-" not in s:
                current["tags"] = []
            elif current.get("tags") is not None and s.startswith("- ") and ":" not in s:
                current["tags"].append(s[2:].strip())
    if current:
        vms.append(current)
    return vms


# ---------------------------------------------------------------------------
# Proxmox live state fetchers
# ---------------------------------------------------------------------------


def _fetch_qm_list() -> list[dict[str, Any]]:
    result = _ssh_to_host("sudo qm list")
    if result.returncode != 0:
        raise RuntimeError(f"qm list failed: {result.stderr.strip()}")
    vms = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.split()
        if len(parts) >= 3:
            try:
                vms.append({"vmid": int(parts[0]), "name": parts[1], "status": parts[2]})
            except (ValueError, IndexError):
                pass
    return vms


def _fetch_qm_config(vmid: int) -> dict[str, Any]:
    result = _ssh_to_host(f"sudo qm config {vmid}")
    if result.returncode != 0:
        raise RuntimeError(f"qm config {vmid} failed: {result.stderr.strip()}")
    config: dict[str, Any] = {}
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        config[key.strip()] = val.strip()
    return config


def _parse_disk_gb(config: dict[str, Any]) -> int | None:
    for disk_key in ("scsi0", "virtio0", "ide0", "sata0"):
        val = config.get(disk_key, "")
        m = re.search(r"size=(\d+(?:\.\d+)?)G", val)
        if m:
            return int(float(m.group(1)))
    return None


def _parse_tags(config: dict[str, Any]) -> list[str]:
    raw = config.get("tags", "")
    return sorted(t.strip() for t in raw.split(";") if t.strip()) if raw else []


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _diff_vm(inv_vm: dict[str, Any], qm_config: dict[str, Any], qm_status: str) -> list[dict[str, Any]]:
    diffs = []

    def _check(field: str, inv_val: Any, live_val: Any) -> None:
        if live_val is None:
            return  # can't determine live value
        if inv_val != live_val:
            diffs.append({"field": field, "inventory": inv_val, "live": live_val, "drift": True})
        else:
            diffs.append({"field": field, "inventory": inv_val, "live": live_val, "drift": False})

    # disk_gb: inventory is in GB, qm config may have MB in some fields
    live_disk = _parse_disk_gb(qm_config)
    _check("disk_gb", inv_vm.get("disk_gb"), live_disk)

    # memory: inventory memory_mb, qm config "memory" in MB
    live_mem = int(qm_config["memory"]) if "memory" in qm_config else None
    _check("memory_mb", inv_vm.get("memory_mb"), live_mem)

    # cores
    live_cores = int(qm_config["cores"]) if "cores" in qm_config else None
    _check("cores", inv_vm.get("cores"), live_cores)

    # name
    live_name = qm_config.get("name")
    _check("name", inv_vm.get("name"), live_name)

    # tags
    inv_tags = sorted(inv_vm.get("tags", []))
    live_tags = _parse_tags(qm_config)
    if inv_tags or live_tags:
        _check("tags", inv_tags, live_tags)

    return diffs


# ---------------------------------------------------------------------------
# sub-command: diff
# ---------------------------------------------------------------------------


def cmd_diff(args: argparse.Namespace) -> int:
    inv_vms = _load_inventory_vms()
    if args.vmid:
        inv_vms = [v for v in inv_vms if v.get("vmid") == args.vmid]
        if not inv_vms:
            raise SystemExit(f"vmid {args.vmid} not in inventory.")

    qm_vms = _fetch_qm_list()
    qm_vm_map = {v["vmid"]: v for v in qm_vms}

    results = []
    any_drift = False
    for inv_vm in inv_vms:
        vmid = inv_vm.get("vmid")
        if vmid not in qm_vm_map:
            results.append({"vmid": vmid, "name": inv_vm.get("name"), "status": "not_found_in_proxmox", "diffs": []})
            continue
        try:
            qm_config = _fetch_qm_config(vmid)
        except RuntimeError as e:
            results.append(
                {"vmid": vmid, "name": inv_vm.get("name"), "status": "config_error", "error": str(e), "diffs": []}
            )
            continue
        diffs = _diff_vm(inv_vm, qm_config, qm_vm_map[vmid].get("status", ""))
        drifted = [d for d in diffs if d.get("drift")]
        if drifted:
            any_drift = True
        results.append(
            {
                "vmid": vmid,
                "name": inv_vm.get("name"),
                "proxmox_status": qm_vm_map[vmid].get("status"),
                "drifted_fields": len(drifted),
                "diffs": diffs,
            }
        )

    print(json.dumps({"results": results, "any_drift": any_drift}, indent=2))
    return 2 if any_drift else 0


# ---------------------------------------------------------------------------
# sub-command: check
# ---------------------------------------------------------------------------


def cmd_check(args: argparse.Namespace) -> int:
    inv_vms = _load_inventory_vms()
    qm_vms = _fetch_qm_list()
    qm_vm_map = {v["vmid"]: v for v in qm_vms}

    drifted_vmids = []
    for inv_vm in inv_vms:
        vmid = inv_vm.get("vmid")
        if vmid not in qm_vm_map:
            continue
        try:
            qm_config = _fetch_qm_config(vmid)
            diffs = _diff_vm(inv_vm, qm_config, "")
            if any(d.get("drift") for d in diffs):
                drifted_vmids.append(vmid)
        except RuntimeError:
            pass

    status = "drifted" if drifted_vmids else "clean"
    print(
        json.dumps(
            {
                "status": status,
                "drifted_vms": drifted_vmids,
                "total_diffs": len(drifted_vmids),
            },
            indent=2,
        )
    )
    return 2 if drifted_vmids else 0


# ---------------------------------------------------------------------------
# sub-command: sync-inventory
# ---------------------------------------------------------------------------


def cmd_sync_inventory(args: argparse.Namespace) -> int:
    inv_vms = _load_inventory_vms()
    target = [v for v in inv_vms if v.get("vmid") == args.vmid]
    if not target:
        raise SystemExit(f"vmid {args.vmid} not in inventory.")
    inv_vm = target[0]

    qm_config = _fetch_qm_config(args.vmid)
    diffs = _diff_vm(inv_vm, qm_config, "")
    drifted = [d for d in diffs if d.get("drift")]

    if not drifted:
        print(json.dumps({"status": "already_clean", "vmid": args.vmid}))
        return 0

    changes = [{"field": d["field"], "from": d["inventory"], "to": d["live"]} for d in drifted]
    if not args.apply:
        print(json.dumps({"status": "dry_run", "vmid": args.vmid, "would_update": changes}))
        print("[dry-run] Pass --apply to write changes.", file=sys.stderr)
        return 0

    # Apply: patch inventory file
    text = TOPOLOGY_HOST_VARS_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    in_block = False
    patched_fields: set[str] = set()
    new_lines = []
    for line in lines:
        s = line.strip()
        if s == f"- vmid: {args.vmid}":
            in_block = True
        elif in_block and s.startswith("- vmid:"):
            in_block = False
        if in_block:
            for change in changes:
                field = change["field"]
                if field in patched_fields:
                    continue
                if field == "tags":
                    continue  # tags are multi-line; skip auto-patch for safety
                if re.match(rf"^\s+{re.escape(field)}:\s+", line):
                    indent = len(line) - len(line.lstrip())
                    live_val = change["to"]
                    line = " " * indent + f"{field}: {live_val}\n"
                    patched_fields.add(field)
        new_lines.append(line)
    TOPOLOGY_HOST_VARS_PATH.write_text("".join(new_lines), encoding="utf-8")
    print(json.dumps({"status": "applied", "vmid": args.vmid, "updated": changes}))
    return 0


# ---------------------------------------------------------------------------
# Parser + main
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="inventory_diff_tool.py",
        description="Diff inventory desired state vs. live Proxmox VM state.",
    )
    subs = p.add_subparsers(dest="command", required=True)

    p_diff = subs.add_parser("diff", help="Full diff of inventory vs. live state.")
    p_diff.add_argument("--vmid", type=int, help="Limit to one VM.")

    subs.add_parser("check", help="Quick pass/fail: is inventory in sync?")

    p_sync = subs.add_parser("sync-inventory", help="Patch inventory to match live state.")
    p_sync.add_argument("--vmid", type=int, required=True)
    p_sync.add_argument("--apply", action="store_true", default=False, help="Write changes (default is dry-run).")

    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "diff":
            return cmd_diff(args)
        if args.command == "check":
            return cmd_check(args)
        if args.command == "sync-inventory":
            return cmd_sync_inventory(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
