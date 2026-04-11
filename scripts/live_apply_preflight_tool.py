#!/usr/bin/env python3
"""live_apply_preflight_tool.py — Pre-flight gate check before any live apply.

QUICKSTART FOR LLMs
-------------------
ALWAYS run this before executing a live apply. It checks all the conditions
that must be true for a safe deployment and returns a GO / NO-GO / WARN verdict.

USAGE EXAMPLES
--------------
  # Full check (recommended before any live apply)
  python3 scripts/live_apply_preflight_tool.py check

  # Check for a specific VM and ADR
  python3 scripts/live_apply_preflight_tool.py check --vmid 120 --adr 0286

  # Individual checks
  python3 scripts/live_apply_preflight_tool.py check-locks --vmid 120
  python3 scripts/live_apply_preflight_tool.py check-capacity --vmid 120
  python3 scripts/live_apply_preflight_tool.py check-conflicts --adr 0286

EXIT CODES
----------
  0 — GO (all checks passed)
  1 — error (tool failure)
  2 — NO-GO or WARN (at least one check failed or warned)
"""

from __future__ import annotations

import argparse
import json
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

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.locking import LockType, ResourceLockRegistry

WORKSTREAMS_PATH = REPO_ROOT / "workstreams.yaml"
CAPACITY_MODEL_PATH = REPO_ROOT / "config" / "capacity-model.json"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
VALIDATION_GATE_PATH = REPO_ROOT / "config" / "validation-gate.json"
PRE_PUSH_HOOK_PATH = REPO_ROOT / ".git" / "hooks" / "pre-push"


# ---------------------------------------------------------------------------
# Individual checks — each returns {"name", "status": ok|warn|fail, "detail"}
# ---------------------------------------------------------------------------


def _check_locks(vmid: int | None) -> dict[str, Any]:
    name = "resource_locks"
    try:
        registry = ResourceLockRegistry(repo_root=REPO_ROOT)
        locks = registry.read_all()
        exclusive = [
            lk
            for lk in locks
            if lk.lock_type == LockType.EXCLUSIVE
            and (vmid is None or lk.resource_path == f"vm:{vmid}" or lk.resource_path.startswith(f"vm:{vmid}/"))
        ]
        if exclusive:
            return {
                "name": name,
                "status": "fail",
                "detail": f"{len(exclusive)} exclusive lock(s) active: "
                + "; ".join(f"{lk.resource_path} by {lk.holder} until {lk.expires_at}" for lk in exclusive),
            }
        return {
            "name": name,
            "status": "ok",
            "detail": f"No exclusive locks on {'vm:' + str(vmid) if vmid else 'any resource'}.",
        }
    except Exception as exc:
        return {"name": name, "status": "warn", "detail": f"Could not read lock registry: {exc}"}


def _check_capacity(vmid: int | None) -> dict[str, Any]:
    name = "capacity"
    if not CAPACITY_MODEL_PATH.exists():
        return {"name": name, "status": "warn", "detail": "capacity-model.json not found."}
    try:
        model = json.loads(CAPACITY_MODEL_PATH.read_text(encoding="utf-8"))
        host = model["host"]
        phys = host["physical"]
        tgt = host.get("target_utilisation", {})
        reserved = host.get("reserved_for_platform", {})
        active = [g for g in model.get("guests", []) if g.get("status") == "active"]

        if vmid:
            vm_guests = [g for g in active if g.get("vmid") == vmid]
            if vm_guests:
                g = vm_guests[0]
                over = [k for k in ("ram_gb", "vcpu", "disk_gb") if g["allocated"].get(k, 0) > g["budget"].get(k, 0)]
                if over:
                    return {
                        "name": name,
                        "status": "warn",
                        "detail": f"vmid {vmid} ({g['name']}) over budget on: {', '.join(over)}",
                    }
                return {"name": name, "status": "ok", "detail": f"vmid {vmid} within budget."}

        # Global headroom check
        total_ram = sum(g["allocated"].get("ram_gb", 0) for g in active)
        target_ram = phys["ram_gb"] * tgt.get("ram_percent", 80) / 100 - reserved.get("ram_gb", 0)
        headroom_pct = (target_ram - total_ram) / phys["ram_gb"] * 100
        if headroom_pct < 10:
            return {
                "name": name,
                "status": "fail",
                "detail": f"RAM headroom critical: {headroom_pct:.1f}% of physical.",
            }
        if headroom_pct < 20:
            return {"name": name, "status": "warn", "detail": f"RAM headroom tight: {headroom_pct:.1f}% of physical."}
        return {"name": name, "status": "ok", "detail": f"RAM headroom {headroom_pct:.1f}% — healthy."}
    except Exception as exc:
        return {"name": name, "status": "warn", "detail": f"Capacity check failed: {exc}"}


def _check_workstream_conflicts(adr: str | None) -> dict[str, Any]:
    name = "workstream_conflicts"
    if not WORKSTREAMS_PATH.exists():
        return {"name": name, "status": "warn", "detail": "workstreams.yaml not found."}
    try:
        try:
            import yaml  # type: ignore[import]

            data = yaml.safe_load(WORKSTREAMS_PATH.read_text(encoding="utf-8"))
        except ImportError:
            return {"name": name, "status": "warn", "detail": "PyYAML not available; skipping conflict check."}

        workstreams = data.get("workstreams", [])
        in_progress = [ws for ws in workstreams if ws.get("status") == "in_progress"]

        if not adr:
            return {
                "name": name,
                "status": "ok",
                "detail": f"{len(in_progress)} workstream(s) in progress; no ADR specified to check conflicts against.",
            }

        # Check if the target ADR has a workstream already in_progress that conflicts
        target_ws = [ws for ws in workstreams if str(ws.get("adr", "")) == str(adr)]
        conflicts = [ws for ws in target_ws if ws.get("conflicts_with")]
        if conflicts:
            return {
                "name": name,
                "status": "warn",
                "detail": f"ADR {adr} workstream has declared conflicts: {conflicts[0]['conflicts_with']}",
            }

        return {
            "name": name,
            "status": "ok",
            "detail": f"No declared conflicts for ADR {adr}. {len(in_progress)} workstream(s) currently in progress.",
        }
    except Exception as exc:
        return {"name": name, "status": "warn", "detail": f"Conflict check failed: {exc}"}


def _check_validation_gate() -> dict[str, Any]:
    name = "validation_gate"
    missing = []
    if not VALIDATION_GATE_PATH.exists():
        missing.append("config/validation-gate.json")
    if not PRE_PUSH_HOOK_PATH.exists():
        missing.append(".git/hooks/pre-push")
    if missing:
        return {"name": name, "status": "warn", "detail": f"Validation gate artifacts missing: {', '.join(missing)}"}
    return {"name": name, "status": "ok", "detail": "Validation gate config and pre-push hook present."}


def _check_uncommitted_inventory() -> dict[str, Any]:
    name = "uncommitted_inventory"
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "inventory/"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=10,
        )
        changed = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        if changed:
            return {"name": name, "status": "warn", "detail": f"Uncommitted inventory changes: {', '.join(changed)}"}
        # Also check staged
        result2 = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "inventory/"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=10,
        )
        staged = [ln.strip() for ln in result2.stdout.splitlines() if ln.strip()]
        if staged:
            return {
                "name": name,
                "status": "warn",
                "detail": f"Staged (not yet committed) inventory changes: {', '.join(staged)}",
            }
        return {"name": name, "status": "ok", "detail": "No uncommitted inventory changes."}
    except Exception as exc:
        return {"name": name, "status": "warn", "detail": f"git diff failed: {exc}"}


def _check_active_lock_count() -> dict[str, Any]:
    name = "total_active_locks"
    try:
        registry = ResourceLockRegistry(repo_root=REPO_ROOT)
        locks = registry.read_all()
        count = len(locks)
        exclusive = sum(1 for lk in locks if lk.lock_type == LockType.EXCLUSIVE)
        if exclusive > 5:
            return {
                "name": name,
                "status": "warn",
                "detail": f"{count} total locks, {exclusive} exclusive — platform is busy.",
            }
        return {"name": name, "status": "ok", "detail": f"{count} total locks, {exclusive} exclusive."}
    except Exception as exc:
        return {"name": name, "status": "warn", "detail": f"Lock count check failed: {exc}"}


# ---------------------------------------------------------------------------
# sub-command: check (full)
# ---------------------------------------------------------------------------


def _run_all_checks(vmid: int | None, adr: str | None) -> list[dict[str, Any]]:
    return [
        _check_locks(vmid),
        _check_capacity(vmid),
        _check_workstream_conflicts(adr),
        _check_validation_gate(),
        _check_uncommitted_inventory(),
        _check_active_lock_count(),
    ]


def _compute_verdict(checks: list[dict]) -> str:
    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        return "NO-GO"
    if "warn" in statuses:
        return "WARN"
    return "GO"


def cmd_check(args: argparse.Namespace) -> int:
    checks = _run_all_checks(args.vmid, args.adr)
    verdict = _compute_verdict(checks)
    print(
        json.dumps(
            {
                "verdict": verdict,
                "timestamp": datetime.now(UTC).isoformat(),
                "vmid": args.vmid,
                "adr": args.adr,
                "checks": checks,
                "summary": {
                    "pass": sum(1 for c in checks if c["status"] == "ok"),
                    "warn": sum(1 for c in checks if c["status"] == "warn"),
                    "fail": sum(1 for c in checks if c["status"] == "fail"),
                },
            },
            indent=2,
        )
    )
    return 0 if verdict == "GO" else 2


def cmd_check_locks(args: argparse.Namespace) -> int:
    result = _check_locks(args.vmid)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 2


def cmd_check_capacity(args: argparse.Namespace) -> int:
    result = _check_capacity(args.vmid)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 2


def cmd_check_conflicts(args: argparse.Namespace) -> int:
    result = _check_workstream_conflicts(args.adr)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 2


# ---------------------------------------------------------------------------
# Parser + main
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="live_apply_preflight_tool.py",
        description="Pre-flight gate check before any live apply. Returns GO/NO-GO/WARN verdict.",
    )
    subs = p.add_subparsers(dest="command", required=True)

    p_check = subs.add_parser("check", help="Run all pre-flight checks (recommended).")
    p_check.add_argument("--vmid", type=int, help="Target VM ID to scope lock and capacity checks.")
    p_check.add_argument("--adr", help="ADR number (e.g. 0286) to check for workstream conflicts.")
    p_check.add_argument("--branch", help="Branch name (informational only, logged in output).")

    p_locks = subs.add_parser("check-locks", help="Only check resource locks.")
    p_locks.add_argument("--vmid", type=int)

    p_cap = subs.add_parser("check-capacity", help="Only check capacity model.")
    p_cap.add_argument("--vmid", type=int)

    p_conf = subs.add_parser("check-conflicts", help="Only check workstream conflicts.")
    p_conf.add_argument("--adr", help="ADR number.")

    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "check":
            return cmd_check(args)
        if args.command == "check-locks":
            return cmd_check_locks(args)
        if args.command == "check-capacity":
            return cmd_check_capacity(args)
        if args.command == "check-conflicts":
            return cmd_check_conflicts(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
