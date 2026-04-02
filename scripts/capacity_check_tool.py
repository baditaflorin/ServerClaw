#!/usr/bin/env python3
"""capacity_check_tool.py — Query host capacity and gate new resource provisioning.

QUICKSTART FOR LLMs
-------------------
Run this BEFORE provisioning a new VM or changing an existing VM's resources.
It reads config/capacity-model.json and tells you whether the host has budget
for the requested allocation.

USAGE EXAMPLES
--------------
  # Full capacity report — see all allocations and headroom
  python3 scripts/capacity_check_tool.py report

  # Quick headroom summary
  python3 scripts/capacity_check_tool.py headroom

  # Gate check before adding a new VM (returns non-zero if capacity exceeded)
  python3 scripts/capacity_check_tool.py check --ram-gb 8 --vcpu 4 --disk-gb 64

  # Single guest view
  python3 scripts/capacity_check_tool.py guest --vmid 120

EXIT CODES
----------
  0 — ok / headroom available
  1 — error (missing file, bad args)
  2 — capacity exceeded or tight (for `check` command)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPACITY_MODEL_PATH = REPO_ROOT / "config" / "capacity-model.json"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_model() -> dict[str, Any]:
    if not CAPACITY_MODEL_PATH.exists():
        raise SystemExit(f"Capacity model not found: {CAPACITY_MODEL_PATH}")
    return json.loads(CAPACITY_MODEL_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Computation helpers
# ---------------------------------------------------------------------------

def _active_guests(model: dict[str, Any]) -> list[dict[str, Any]]:
    return [g for g in model.get("guests", []) if g.get("status") == "active"]


def _sum_allocated(guests: list[dict[str, Any]]) -> dict[str, float]:
    ram = sum(g["allocated"].get("ram_gb", 0) for g in guests)
    vcpu = sum(g["allocated"].get("vcpu", 0) for g in guests)
    disk = sum(g["allocated"].get("disk_gb", 0) for g in guests)
    return {"ram_gb": ram, "vcpu": vcpu, "disk_gb": disk}


def _sum_budgeted(guests: list[dict[str, Any]]) -> dict[str, float]:
    ram = sum(g["budget"].get("ram_gb", 0) for g in guests)
    vcpu = sum(g["budget"].get("vcpu", 0) for g in guests)
    disk = sum(g["budget"].get("disk_gb", 0) for g in guests)
    return {"ram_gb": ram, "vcpu": vcpu, "disk_gb": disk}


def _compute_headroom(model: dict[str, Any], allocated: dict[str, float]) -> dict[str, float]:
    host = model["host"]
    phys = host["physical"]
    tgt = host["target_utilisation"]
    reserved = host.get("reserved_for_platform", {})
    target_ram = phys["ram_gb"] * tgt["ram_percent"] / 100
    target_vcpu = phys["vcpu"] * tgt["vcpu_percent"] / 100
    target_disk = phys["disk_gb"] * tgt["disk_percent"] / 100
    res_ram = reserved.get("ram_gb", 0)
    res_vcpu = reserved.get("vcpu", 0)
    res_disk = reserved.get("disk_gb", 0)
    return {
        "ram_gb": round(target_ram - res_ram - allocated["ram_gb"], 1),
        "vcpu": round(target_vcpu - res_vcpu - allocated["vcpu"], 1),
        "disk_gb": round(target_disk - res_disk - allocated["disk_gb"], 1),
    }


def _headroom_status(model: dict[str, Any], headroom: dict[str, float]) -> str:
    phys = model["host"]["physical"]
    pct_ram = headroom["ram_gb"] / phys["ram_gb"] * 100
    pct_vcpu = headroom["vcpu"] / phys["vcpu"] * 100
    pct_disk = headroom["disk_gb"] / phys["disk_gb"] * 100
    if min(pct_ram, pct_vcpu, pct_disk) < 10:
        return "critical"
    if min(pct_ram, pct_vcpu, pct_disk) < 20:
        return "tight"
    return "healthy"


# ---------------------------------------------------------------------------
# sub-command: report
# ---------------------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> int:
    model = _load_model()
    active = _active_guests(model)
    allocated = _sum_allocated(active)
    budgeted = _sum_budgeted(active)
    headroom = _compute_headroom(model, allocated)
    host = model["host"]
    phys = host["physical"]

    guests_out = []
    for g in active:
        alloc = g["allocated"]
        budget = g["budget"]
        over = (
            alloc.get("ram_gb", 0) > budget.get("ram_gb", 0)
            or alloc.get("vcpu", 0) > budget.get("vcpu", 0)
            or alloc.get("disk_gb", 0) > budget.get("disk_gb", 0)
        )
        guests_out.append({
            "vmid": g.get("vmid"),
            "name": g.get("name"),
            "environment": g.get("environment"),
            "allocated": alloc,
            "budget": budget,
            "over_budget": over,
        })

    warnings = [
        f"{g['name']} exceeds budget on: "
        + ", ".join(
            k for k in ("ram_gb", "vcpu", "disk_gb")
            if g["allocated"].get(k, 0) > g["budget"].get(k, 0)
        )
        for g in active
        if any(g["allocated"].get(k, 0) > g["budget"].get(k, 0) for k in ("ram_gb", "vcpu", "disk_gb"))
    ]

    print(json.dumps({
        "host": {
            "id": host.get("id"),
            "physical": phys,
            "target_utilisation": host.get("target_utilisation"),
            "reserved_for_platform": host.get("reserved_for_platform"),
        },
        "active_guest_count": len(active),
        "allocated": allocated,
        "budgeted": budgeted,
        "headroom": headroom,
        "headroom_status": _headroom_status(model, headroom),
        "guests": guests_out,
        "warnings": warnings,
    }, indent=2))
    return 0


# ---------------------------------------------------------------------------
# sub-command: headroom
# ---------------------------------------------------------------------------

def cmd_headroom(args: argparse.Namespace) -> int:
    model = _load_model()
    active = _active_guests(model)
    allocated = _sum_allocated(active)
    headroom = _compute_headroom(model, allocated)
    status = _headroom_status(model, headroom)
    print(json.dumps({
        "ram_gb_free": headroom["ram_gb"],
        "vcpu_free": headroom["vcpu"],
        "disk_gb_free": headroom["disk_gb"],
        "status": status,
        "note": (
            "critical: at least one resource < 10% of physical capacity"
            if status == "critical"
            else "tight: at least one resource < 20% of physical capacity"
            if status == "tight"
            else "healthy: all resources above 20% of physical capacity"
        ),
    }, indent=2))
    return 2 if status in ("critical", "tight") else 0


# ---------------------------------------------------------------------------
# sub-command: check
# ---------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    if not any([args.ram_gb, args.vcpu, args.disk_gb]):
        raise SystemExit("Provide at least one of --ram-gb, --vcpu, --disk-gb.")

    model = _load_model()
    active = _active_guests(model)
    allocated = _sum_allocated(active)
    headroom = _compute_headroom(model, allocated)

    requested: dict[str, float] = {
        "ram_gb": args.ram_gb or 0,
        "vcpu": args.vcpu or 0,
        "disk_gb": args.disk_gb or 0,
    }
    after: dict[str, float] = {k: round(headroom[k] - requested[k], 1) for k in requested}

    shortfalls = [k for k, v in after.items() if v < 0]
    verdict = "fail" if shortfalls else ("warn" if _headroom_status(model, headroom) == "tight" else "ok")
    reason = (
        f"Insufficient capacity for: {', '.join(shortfalls)}"
        if shortfalls
        else "Capacity available within target utilisation."
    )

    out = {
        "verdict": verdict,
        "reason": reason,
        "current_headroom": headroom,
        "requested": requested,
        "headroom_after_add": after,
        "would_exceed_target": bool(shortfalls),
    }
    print(json.dumps(out, indent=2))
    return 2 if verdict == "fail" else 0


# ---------------------------------------------------------------------------
# sub-command: guest
# ---------------------------------------------------------------------------

def cmd_guest(args: argparse.Namespace) -> int:
    model = _load_model()
    matches = [g for g in model.get("guests", []) if g.get("vmid") == args.vmid]
    if not matches:
        raise SystemExit(f"vmid {args.vmid} not in capacity model.")
    g = matches[0]
    alloc = g["allocated"]
    budget = g["budget"]

    def pct(a: float, b: float) -> float:
        return round(a / b * 100, 1) if b else 0.0

    print(json.dumps({
        "vmid": g.get("vmid"),
        "name": g.get("name"),
        "status": g.get("status"),
        "environment": g.get("environment"),
        "allocated": alloc,
        "budget": budget,
        "utilisation": {
            "ram_pct": pct(alloc.get("ram_gb", 0), budget.get("ram_gb", 1)),
            "vcpu_pct": pct(alloc.get("vcpu", 0), budget.get("vcpu", 1)),
            "disk_pct": pct(alloc.get("disk_gb", 0), budget.get("disk_gb", 1)),
        },
        "over_budget": any(
            alloc.get(k, 0) > budget.get(k, 0) for k in ("ram_gb", "vcpu", "disk_gb")
        ),
        "notes": g.get("notes", ""),
    }, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Parser + main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="capacity_check_tool.py",
        description="Query host capacity and gate new resource provisioning.",
    )
    subs = p.add_subparsers(dest="command", required=True)

    subs.add_parser("report", help="Full capacity report — all allocations and headroom.")
    subs.add_parser("headroom", help="Quick headroom summary (returns non-zero if tight/critical).")

    p_check = subs.add_parser("check", help="Gate check before adding a new VM or resource.")
    p_check.add_argument("--ram-gb", type=float, metavar="N")
    p_check.add_argument("--vcpu", type=float, metavar="N")
    p_check.add_argument("--disk-gb", type=float, metavar="N")

    p_guest = subs.add_parser("guest", help="Per-guest capacity view.")
    p_guest.add_argument("--vmid", type=int, required=True)

    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "report":
            return cmd_report(args)
        if args.command == "headroom":
            return cmd_headroom(args)
        if args.command == "check":
            return cmd_check(args)
        if args.command == "guest":
            return cmd_guest(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
