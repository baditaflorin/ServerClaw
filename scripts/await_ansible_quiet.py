#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessEntry:
    pid: int
    ppid: int
    command: str


def parse_process_table(raw: str) -> list[ProcessEntry]:
    entries: list[ProcessEntry] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(maxsplit=2)
        if len(parts) != 3:
            continue
        pid_raw, ppid_raw, command = parts
        try:
            pid = int(pid_raw)
            ppid = int(ppid_raw)
        except ValueError:
            continue
        entries.append(ProcessEntry(pid=pid, ppid=ppid, command=command))
    return entries


def read_process_table() -> list[ProcessEntry]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="],
        capture_output=True,
        check=True,
        text=True,
    )
    return parse_process_table(result.stdout)


def tokenize_command(command: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(command))
    except ValueError:
        return tuple(command.split())


def is_ansible_playbook_process(entry: ProcessEntry) -> bool:
    tokens = tokenize_command(entry.command)
    for index, token in enumerate(tokens):
        base = token.rsplit("/", 1)[-1]
        if base != "ansible-playbook":
            continue
        if token != "ansible-playbook":
            return True
        if index == 0:
            return True
        if tokens[0].rsplit("/", 1)[-1] == "uv":
            return True
    return False


def ancestor_pids(entries: list[ProcessEntry], start_pid: int) -> set[int]:
    parents = {entry.pid: entry.ppid for entry in entries}
    visited: set[int] = set()
    current = start_pid
    while current > 0 and current not in visited:
        visited.add(current)
        next_pid = parents.get(current)
        if next_pid is None or next_pid == current:
            break
        current = next_pid
    return visited


def find_blocking_processes(
    entries: list[ProcessEntry],
    *,
    required_hosts: tuple[str, ...],
    ignored_pids: set[int],
) -> list[ProcessEntry]:
    blockers: list[ProcessEntry] = []
    for entry in entries:
        if entry.pid in ignored_pids:
            continue
        if not is_ansible_playbook_process(entry):
            continue
        if not any(host in entry.command for host in required_hosts):
            continue
        blockers.append(entry)
    return sorted(blockers, key=lambda item: item.pid)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Wait for other controller-local ansible-playbook processes touching the "
            "same hosts to clear before continuing."
        )
    )
    parser.add_argument("--host", action="append", dest="hosts", required=True, help="Required host to watch.")
    parser.add_argument("--label", default="ansible-quiet-window", help="Human-readable label for log messages.")
    parser.add_argument("--wait-seconds", type=float, default=900.0, help="Maximum total wait time.")
    parser.add_argument("--quiet-seconds", type=float, default=30.0, help="Continuous quiet time required.")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Polling interval while waiting.")
    return parser


def format_blockers(blockers: list[ProcessEntry]) -> str:
    return "\n".join(f"  pid={entry.pid} ppid={entry.ppid} command={entry.command}" for entry in blockers)


def main() -> int:
    args = build_parser().parse_args()
    required_hosts = tuple(host.strip() for host in args.hosts if host.strip())
    if not required_hosts:
        raise SystemExit("At least one non-empty --host value is required.")

    deadline = time.monotonic() + max(args.wait_seconds, 0.0)
    quiet_start: float | None = None
    last_snapshot: tuple[tuple[int, int, str], ...] | None = None

    while True:
        entries = read_process_table()
        ignored_pids = ancestor_pids(entries, os.getpid())
        blockers = find_blocking_processes(entries, required_hosts=required_hosts, ignored_pids=ignored_pids)
        snapshot = tuple((entry.pid, entry.ppid, entry.command) for entry in blockers)

        if blockers:
            quiet_start = None
            if snapshot != last_snapshot:
                print(
                    f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] waiting for {args.label}: "
                    f"{len(blockers)} conflicting ansible-playbook process(es)",
                    file=sys.stderr,
                )
                print(format_blockers(blockers), file=sys.stderr)
                last_snapshot = snapshot
            if time.monotonic() >= deadline:
                print(f"Timed out waiting for a quiet controller window for {args.label}.", file=sys.stderr)
                return 1
            time.sleep(max(args.poll_seconds, 0.1))
            continue

        if quiet_start is None:
            quiet_start = time.monotonic()
        if time.monotonic() - quiet_start >= max(args.quiet_seconds, 0.0):
            print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] quiet window acquired for {args.label}", file=sys.stderr)
            return 0
        time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    raise SystemExit(main())
