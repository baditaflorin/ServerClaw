#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from controller_automation_toolkit import emit_cli_error
from platform.scheduler import load_execution_lanes


def list_lanes() -> int:
    lanes = load_execution_lanes(repo_root=REPO_ROOT)
    print(f"Execution lanes: {REPO_ROOT / 'config' / 'execution-lanes.yaml'}")
    for lane_id, lane in sorted(lanes.items()):
        print(
            f"  - {lane_id}: {lane.hostname} "
            f"[ops={lane.max_concurrent_ops}, policy={lane.admission_policy}, "
            f"cpu={lane.budget.total_cpu_milli}, mem={lane.budget.total_memory_mb}, iops={lane.budget.total_disk_iops}]"
        )
    return 0


def show_lane(lane_id: str) -> int:
    lanes = load_execution_lanes(repo_root=REPO_ROOT)
    lane = lanes.get(lane_id)
    if lane is None:
        print(f"Unknown execution lane: {lane_id}", file=sys.stderr)
        return 2
    print(f"Lane: {lane.lane_id}")
    print(f"Hostname: {lane.hostname}")
    print(f"VM ID: {lane.vm_id}")
    print(f"Max concurrent ops: {lane.max_concurrent_ops}")
    print(f"Serialisation: {lane.serialisation}")
    print(f"Admission policy: {lane.admission_policy}")
    print("VM budget:")
    for key, value in lane.budget.as_dict().items():
        print(f"  - {key}: {value}")
    print("Services:")
    if lane.services:
        for service in lane.services:
            print(f"  - {service}")
    else:
        print("  - none")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or validate the scheduler execution-lane catalog.")
    parser.add_argument("--list", action="store_true", help="List execution lanes.")
    parser.add_argument("--lane", help="Show one execution lane.")
    parser.add_argument("--validate", action="store_true", help="Validate the execution-lane catalog.")
    args = parser.parse_args()

    try:
        lanes = load_execution_lanes(repo_root=REPO_ROOT)
    except (OSError, ValueError) as exc:
        return emit_cli_error("Execution lanes", exc)

    if args.validate:
        print(f"Execution lanes OK: {REPO_ROOT / 'config' / 'execution-lanes.yaml'} ({len(lanes)} lane(s))")
        return 0
    if args.lane:
        return show_lane(args.lane)
    return list_lanes()


if __name__ == "__main__":
    raise SystemExit(main())
