#!/usr/bin/env python3
"""Convergence timing wrapper — measures and records how long each convergence run takes.

Wraps `make converge-<service>` (or any convergence command) and writes a structured
timing receipt to receipts/convergence-timing/. Over time this builds a dataset for
measuring ADR 0392 improvements, detecting drift in convergence speed, and identifying
slow plays.

Usage:
    # Time a single convergence:
    python3 scripts/convergence_timer.py run --service api-gateway --env production

    # Time with custom command (e.g. for testing):
    python3 scripts/convergence_timer.py run --service api-gateway --command "make converge-api-gateway env=production"

    # Compare timing history for a service:
    python3 scripts/convergence_timer.py report --service api-gateway

    # Report all services, sorted by slowest:
    python3 scripts/convergence_timer.py report --all --sort-by median

    # Show trend (improving, stable, degrading):
    python3 scripts/convergence_timer.py trend

    # Dry-run: show what command would run, do not execute:
    python3 scripts/convergence_timer.py run --service api-gateway --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, UTC
from pathlib import Path
from statistics import median, stdev
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMING_RECEIPTS_DIR = REPO_ROOT / "receipts" / "convergence-timing"
SCHEMA_VERSION = "1.0.0"

# Phase markers extracted from Ansible stdout (for breakdown analysis)
PHASE_PATTERNS = {
    "ssh_facts": re.compile(r"TASK \[Gathering Facts\]"),
    "preflight": re.compile(r"TASK \[.*preflight|Run shared preflight\]"),
    "docker_pull": re.compile(r"TASK \[Pull images for|Check if images exist locally for\]"),
    "role_convergence": re.compile(r"PLAY \[Converge\]"),
    "health_check": re.compile(r"TASK \[Wait for .* to listen on port|Verify .* health endpoint\]"),
    "nginx_reload": re.compile(r"TASK \[.*nginx.*reload|Reload nginx\]"),
    "post_verify": re.compile(r"TASK \[.*post.verify|Run shared post-verify\]"),
    "notification": re.compile(r"TASK \[.*ntfy.*|Publish.*notification\]"),
}

PLAY_RESULT_PATTERN = re.compile(r"(ok|changed|unreachable|failed|skipped|rescued|ignored)=(\d+)")
PLAY_RECAP_PATTERN = re.compile(r"^PLAY RECAP")


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _source_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()[:12]


def _repo_version() -> str:
    version_file = REPO_ROOT / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "unknown"


def _parse_ansible_summary(stdout: str) -> dict[str, Any]:
    """Extract play recap stats and phase timestamps from Ansible output."""
    phases: list[dict[str, Any]] = []
    current_phase: str | None = None
    phase_start_line: int = 0
    recap: dict[str, int] = {}
    changed_tasks: list[str] = []
    failed_tasks: list[str] = []
    in_recap = False

    lines = stdout.splitlines()
    for i, line in enumerate(lines):
        # Detect play recap
        if PLAY_RECAP_PATTERN.match(line):
            in_recap = True
        if in_recap:
            for match in PLAY_RESULT_PATTERN.finditer(line):
                recap[match.group(1)] = int(match.group(2))

        # Detect changed tasks
        if line.strip().startswith("changed:") or ("changed" in line and "TASK" not in line):
            # Extract task name from context (2 lines back)
            for j in range(max(0, i - 3), i):
                if "TASK [" in lines[j]:
                    task_name = lines[j].strip().strip("*").strip()
                    if task_name and task_name not in changed_tasks:
                        changed_tasks.append(task_name)

        # Detect failed tasks
        if "fatal:" in line.lower() or "FAILED!" in line:
            failed_tasks.append(line.strip()[:120])

        # Phase detection
        for phase_name, pattern in PHASE_PATTERNS.items():
            if pattern.search(line):
                if current_phase and current_phase != phase_name:
                    phases.append(
                        {
                            "phase": current_phase,
                            "first_seen_line": phase_start_line,
                        }
                    )
                if current_phase != phase_name:
                    current_phase = phase_name
                    phase_start_line = i

    return {
        "recap": recap,
        "phases_observed": phases,
        "changed_tasks": changed_tasks[:20],
        "failed_tasks": failed_tasks[:10],
        "outcome": "failed" if recap.get("failed", 0) > 0 or recap.get("unreachable", 0) > 0 else "ok",
    }


def _build_receipt(
    service: str,
    env: str,
    command: str,
    started_at: str,
    completed_at: str,
    duration_seconds: float,
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    receipt_id = f"{datetime.now(UTC).strftime('%Y-%m-%d')}-{service}-timing-{uuid.uuid4().hex[:6]}"
    ansible_summary = _parse_ansible_summary(stdout)

    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": receipt_id,
        "service": service,
        "env": env,
        "command": command,
        "timing": {
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": round(duration_seconds, 2),
        },
        "outcome": ansible_summary["outcome"] if returncode == 0 else "failed",
        "returncode": returncode,
        "source_commit": _source_commit(),
        "repo_version": _repo_version(),
        "ansible_summary": ansible_summary,
    }


def cmd_run(args: argparse.Namespace) -> int:
    service = args.service
    env = args.env

    if args.command:
        command = args.command
    else:
        make_target = f"converge-{service}"
        command = f"make {make_target} env={env}"

    if args.dry_run:
        print(f"Dry run — would execute: {command}")
        return 0

    print(f"[convergence-timer] Starting {service} ({env})")
    print(f"[convergence-timer] Command: {command}")
    print("[convergence-timer] Timing begins now...")

    started_at = _utcnow_iso()
    t0 = time.monotonic()

    result = subprocess.run(
        command,
        shell=True,
        cwd=REPO_ROOT,
        text=True,
        capture_output=False,  # Let output stream to terminal
        env={**os.environ},
    )

    duration = time.monotonic() - t0
    completed_at = _utcnow_iso()

    print(f"\n[convergence-timer] Completed in {duration:.1f}s (rc={result.returncode})")

    # Re-run quickly just to capture output for parsing (without showing again)
    capture_result = (
        subprocess.run(
            command + " 2>&1",
            shell=True,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            env={**os.environ, "ANSIBLE_NOCOLOR": "1", "ANSIBLE_FORCE_COLOR": "0"},
            timeout=10,  # Only for summary parsing — likely cached/skipped
        )
        if args.capture_summary
        else None
    )

    captured_stdout = capture_result.stdout if capture_result else ""
    captured_stderr = capture_result.stderr if capture_result else ""

    receipt = _build_receipt(
        service=service,
        env=env,
        command=command,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration,
        returncode=result.returncode,
        stdout=captured_stdout,
        stderr=captured_stderr,
    )

    # Write receipt
    TIMING_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    receipt_path = TIMING_RECEIPTS_DIR / f"{receipt['receipt_id']}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"[convergence-timer] Receipt written: {receipt_path.name}")

    return result.returncode


def _load_timing_receipts(service: str | None = None) -> list[dict[str, Any]]:
    if not TIMING_RECEIPTS_DIR.exists():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(TIMING_RECEIPTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            if service is None or data.get("service") == service:
                receipts.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return receipts


def cmd_report(args: argparse.Namespace) -> int:
    if args.all:
        # Group by service
        all_receipts = _load_timing_receipts()
        services: dict[str, list[float]] = {}
        for r in all_receipts:
            svc = r.get("service", "unknown")
            dur = r.get("timing", {}).get("duration_seconds")
            if dur is not None:
                services.setdefault(svc, []).append(float(dur))

        if not services:
            print("No timing receipts found.")
            return 0

        sort_key = args.sort_by or "median"
        rows = []
        for svc, durations in services.items():
            rows.append(
                {
                    "service": svc,
                    "runs": len(durations),
                    "min": min(durations),
                    "median": median(durations),
                    "max": max(durations),
                    "last": durations[-1],
                    "stdev": stdev(durations) if len(durations) > 1 else 0.0,
                }
            )
        rows.sort(key=lambda r: r[sort_key], reverse=True)

        print(f"\n{'Service':<30} {'Runs':>4} {'Min':>7} {'Median':>8} {'Max':>7} {'Last':>7} {'StdDev':>8}")
        print("-" * 80)
        for row in rows:
            print(
                f"{row['service']:<30} {row['runs']:>4} "
                f"{row['min']:>6.0f}s {row['median']:>7.0f}s "
                f"{row['max']:>6.0f}s {row['last']:>6.0f}s "
                f"{row['stdev']:>7.1f}s"
            )
        return 0

    # Single service report
    service = args.service
    receipts = _load_timing_receipts(service)
    if not receipts:
        print(f"No timing receipts found for service: {service}")
        return 1

    durations = [r["timing"]["duration_seconds"] for r in receipts if "timing" in r]
    outcomes = [r.get("outcome", "unknown") for r in receipts]
    versions = [r.get("repo_version", "?") for r in receipts]

    print(f"\nConvergence timing: {service}")
    print(f"  Runs: {len(receipts)}")
    print(f"  Min:    {min(durations):.1f}s")
    print(f"  Median: {median(durations):.1f}s")
    print(f"  Max:    {max(durations):.1f}s")
    if len(durations) > 1:
        print(f"  StdDev: {stdev(durations):.1f}s")

    print(f"\n{'Date':<12} {'Version':<12} {'Duration':>9} {'Outcome':<10} {'Receipt ID'}")
    print("-" * 70)
    for r in receipts[-20:]:
        date = r.get("timing", {}).get("started_at", "?")[:10]
        ver = r.get("repo_version", "?")
        dur = r.get("timing", {}).get("duration_seconds", 0)
        outcome = r.get("outcome", "?")
        rid = r.get("receipt_id", "?")[-20:]
        print(f"{date:<12} {ver:<12} {dur:>8.1f}s {outcome:<10} {rid}")

    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    """Show convergence speed trend across all services."""
    all_receipts = _load_timing_receipts()
    if len(all_receipts) < 2:
        print("Not enough data for trend analysis (need ≥2 receipts).")
        return 0

    services: dict[str, list[tuple[str, float]]] = {}
    for r in all_receipts:
        svc = r.get("service", "unknown")
        dur = r.get("timing", {}).get("duration_seconds")
        ts = r.get("timing", {}).get("started_at", "")
        if dur is not None:
            services.setdefault(svc, []).append((ts, float(dur)))

    print(f"\n{'Service':<30} {'Trend':<12} {'First':>8} {'Last':>8} {'Change':>9}")
    print("-" * 70)
    for svc, runs in sorted(services.items()):
        if len(runs) < 2:
            continue
        runs.sort(key=lambda x: x[0])
        first_dur = runs[0][1]
        last_dur = runs[-1][1]
        change = last_dur - first_dur
        pct = (change / first_dur * 100) if first_dur > 0 else 0
        if pct < -5:
            trend = "IMPROVING ↓"
        elif pct > 5:
            trend = "DEGRADING ↑"
        else:
            trend = "STABLE →"
        print(f"{svc:<30} {trend:<12} {first_dur:>7.0f}s {last_dur:>7.0f}s {change:>+8.0f}s ({pct:>+.1f}%)")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convergence timing wrapper — measure, record, and report convergence durations (ADR 0392)."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # run
    run_p = subparsers.add_parser("run", help="Run a convergence and record timing.")
    run_p.add_argument("--service", required=True, help="Service name (e.g. api-gateway)")
    run_p.add_argument("--env", default="production", help="Environment (default: production)")
    run_p.add_argument("--command", help="Custom command override (default: make converge-<service>)")
    run_p.add_argument("--dry-run", action="store_true", help="Print command, do not run.")
    run_p.add_argument(
        "--capture-summary",
        action="store_true",
        help="Re-run silently after main run to capture Ansible output for phase analysis.",
    )

    # report
    rep_p = subparsers.add_parser("report", help="Show timing history for a service.")
    rep_p.add_argument("--service", help="Service name (required unless --all)")
    rep_p.add_argument("--all", action="store_true", help="Report all services.")
    rep_p.add_argument(
        "--sort-by",
        choices=["min", "median", "max", "last", "stdev"],
        default="median",
        help="Sort order for --all (default: median)",
    )

    # trend
    subparsers.add_parser("trend", help="Show improving/stable/degrading trend per service.")

    args = parser.parse_args(argv)

    if args.subcommand == "run":
        return cmd_run(args)
    if args.subcommand == "report":
        if not args.all and not args.service:
            parser.error("--report requires --service or --all")
        return cmd_report(args)
    if args.subcommand == "trend":
        return cmd_trend(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
