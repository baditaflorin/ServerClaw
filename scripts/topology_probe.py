#!/usr/bin/env python3
"""ADR 0443 — guest-side topology probe.

Captures a JSON snapshot of what the local host is actually running:
docker containers and listening TCP ports. Designed to run on every
managed guest (runtime-control, postgres-vm, nginx, etc.) without any
Ansible converge or third-party dependencies — Python 3 stdlib only.

The reconciler (scripts/topology_reconciler.py) shells into each host
and runs this script over SSH, then diffs the result against
platform_service_registry.

Usage:
    python3 scripts/topology_probe.py
        Prints JSON to stdout. Exit 0 always (probe never errors out;
        missing tools become null fields).

    python3 scripts/topology_probe.py --pretty
        Indented JSON for human inspection.

Schema: topology-probe/v1.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import socket
import subprocess
import sys
from typing import Any


SCHEMA = "topology-probe/v1"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str], *, timeout: float = 5.0) -> str | None:
    """Run a command, return stdout on success, None on any failure.

    The probe must be robust: a missing binary or non-zero exit must
    degrade gracefully so the reconciler still gets partial signal.
    """
    if shutil.which(cmd[0]) is None:
        return None
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _docker_containers() -> list[dict[str, Any]] | None:
    """Read running containers via `docker ps`. Returns None if docker is
    unavailable (the host doesn't run containers). Empty list means
    docker is present but no containers are running.
    """
    out = _run(["docker", "ps", "--format", "{{json .}}"], timeout=10.0)
    if out is None:
        return None
    containers = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        containers.append(
            {
                "name": entry.get("Names", ""),
                "image": entry.get("Image", ""),
                "state": entry.get("State", ""),
                "status": entry.get("Status", ""),
                "ports": _parse_docker_ports(entry.get("Ports", "")),
                "labels": _parse_docker_labels(entry.get("Labels", "")),
            }
        )
    return containers


def _parse_docker_ports(raw: str) -> list[str]:
    """`docker ps` formats ports as a comma-separated list. Normalize to
    canonical "host:port->container:port/proto" tokens.
    """
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _parse_docker_labels(raw: str) -> dict[str, str]:
    """Labels are a comma-separated `key=value` list. Skip malformed."""
    out: dict[str, str] = {}
    if not raw:
        return out
    for token in raw.split(","):
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        out[k.strip()] = v.strip()
    return out


# --------------------------------------------------------------------------
# Listening TCP ports
# --------------------------------------------------------------------------

_SS_LISTEN_RE = re.compile(
    r"^LISTEN\s+\S+\s+\S+\s+(?P<addr>\S+):(?P<port>\d+)\s+",
    re.MULTILINE,
)


def _listening_tcp() -> list[dict[str, Any]] | None:
    """Prefer `ss -tlnp4` (or `ss -tlnp`). Fall back to /proc/net/tcp.
    Returns None only if both methods fail.
    """
    out = _run(["ss", "-tln"], timeout=5.0)
    if out is not None:
        return _parse_ss(out)
    return _parse_proc_net_tcp()


def _parse_ss(text: str) -> list[dict[str, Any]]:
    """Parse `ss -tln` text output into a list of {address, port}."""
    listeners: list[dict[str, Any]] = []
    for line in text.splitlines()[1:]:  # skip header
        cols = line.split()
        if len(cols) < 4:
            continue
        if cols[0] != "LISTEN":
            continue
        local = cols[3]
        # local is "address:port" or "[::]:port" or "*:port"
        if local.startswith("["):
            # IPv6 literal: [addr]:port
            close = local.rfind("]")
            addr = local[1:close]
            port_part = local[close + 2 :]
        else:
            addr, _, port_part = local.rpartition(":")
        try:
            port = int(port_part)
        except ValueError:
            continue
        listeners.append({"address": addr or "*", "port": port, "protocol": "tcp"})
    # de-dup (ss can emit ipv4 + ipv6 for the same wildcard listener)
    seen: set[tuple[str, int]] = set()
    deduped = []
    for entry in listeners:
        key = (entry["address"], entry["port"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return sorted(deduped, key=lambda e: e["port"])


def _parse_proc_net_tcp() -> list[dict[str, Any]] | None:
    """Fallback when `ss` isn't installed. Reads /proc/net/tcp + /proc/net/tcp6."""
    listeners: list[dict[str, Any]] = []
    for path, family in [("/proc/net/tcp", "ipv4"), ("/proc/net/tcp6", "ipv6")]:
        try:
            with open(path) as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for line in lines[1:]:
            cols = line.split()
            if len(cols) < 4:
                continue
            if cols[3] != "0A":  # TCP_LISTEN
                continue
            local = cols[1]
            try:
                addr_hex, port_hex = local.split(":")
                port = int(port_hex, 16)
            except ValueError:
                continue
            addr = "*" if set(addr_hex) <= {"0"} else f"<{family}>"
            listeners.append({"address": addr, "port": port, "protocol": "tcp"})
    if not listeners:
        return None
    seen: set[tuple[str, int]] = set()
    deduped = []
    for entry in listeners:
        key = (entry["address"], entry["port"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return sorted(deduped, key=lambda e: e["port"])


# --------------------------------------------------------------------------
# Snapshot assembly
# --------------------------------------------------------------------------


def build_snapshot() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "hostname": socket.gethostname(),
        "captured_at": _utc_now_iso(),
        "containers": _docker_containers(),
        "listening_tcp": _listening_tcp(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pretty", action="store_true", help="Emit indented JSON for human inspection.")
    args = parser.parse_args(argv)

    snapshot = build_snapshot()
    if args.pretty:
        json.dump(snapshot, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        json.dump(snapshot, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
