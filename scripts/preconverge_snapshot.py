#!/usr/bin/env python3
"""Pre-converge host state snapshot for triage / rollback.

ADR 0468 — capture a small, stable subset of the target host's state
before any converge runs so post-converge diffs and incident triage
have a baseline. Receipt schema:

    receipts/pre-converge-state/<host>-<run_id>.json
    {
      "schema_version": "1.0.0",
      "host": "<inventory_hostname>",
      "run_id": "<run_id>",
      "captured_at": "<UTC iso>",
      "systemd_units": [{"unit": "...", "load": "...", "active": "...", "sub": "..."}, ...],
      "docker_containers": [{"name": "...", "image": "...", "status": "..."}, ...],
      "managed_files": [{"path": "...", "sha256": "...", "size_bytes": ..., "mtime": "..."}, ...]
    }

The snapshot is intended to be created by an Ansible task that
captures `systemctl list-unit-files`, `docker ps`, and managed-file
hashes (read via the role-declared list of paths) and pipes the
output through this script's `compose` subcommand.

Usage:

    # From a role's pre_tasks:
    python3 scripts/preconverge_snapshot.py compose \\
        --run-id <run_id> --host <host> --role <role> \\
        --systemd-units-json <path> \\
        --docker-containers-json <path> \\
        --managed-files-json <path> \\
        --receipts-dir receipts/pre-converge-state/

The snapshot is read-only by design — `rollback` is **not** an
automatic operation. Operators inspect the receipt with
`jq receipts/pre-converge-state/<host>-<run_id>.json` and decide
manually what to revert.

Future: a `--diff <run_id>` mode that reads the matching
post-converge receipt (ADR 0466) and shows what changed; not in
this ADR.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPTS_DIR = REPO_ROOT / "receipts" / "pre-converge-state"


def _read_json(path: Path) -> object:
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _cmd_compose(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from check_receipt_freshness import write_receipt_atomic

    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    safe_host = args.host.replace("/", "_")[:64]
    safe_run = args.run_id.replace("/", "_")[:64]
    receipt_path = args.receipts_dir / f"{safe_host}-{safe_run}.json"
    payload = {
        "schema_version": "1.0.0",
        "host": args.host,
        "run_id": args.run_id,
        "role": args.role,
        "captured_at": now,
        "systemd_units": _read_json(args.systemd_units_json) or [],
        "docker_containers": _read_json(args.docker_containers_json) or [],
        "managed_files": _read_json(args.managed_files_json) or [],
    }
    write_receipt_atomic(receipt_path, payload)
    try:
        print(str(receipt_path.relative_to(REPO_ROOT)))
    except ValueError:
        print(str(receipt_path))
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    """Pretty-print one or more pre-converge snapshots."""
    paths: list[Path] = []
    if args.path:
        paths.append(args.path)
    elif args.host:
        for p in sorted(args.receipts_dir.glob(f"{args.host}-*.json")):
            paths.append(p)
    else:
        print("inspect: pass --path or --host", file=sys.stderr)
        return 2
    if not paths:
        print(f"no snapshots found for host={args.host!r}", file=sys.stderr)
        return 1
    for p in paths:
        payload = json.loads(p.read_text())
        print(f"=== {p.name} ===")
        print(f"  host={payload['host']} run_id={payload['run_id']} role={payload.get('role', '?')}")
        print(f"  captured_at={payload['captured_at']}")
        print(f"  systemd_units={len(payload['systemd_units'])}  docker_containers={len(payload['docker_containers'])}  managed_files={len(payload['managed_files'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_compose = sub.add_parser("compose", help="Build a snapshot receipt from JSON inputs")
    p_compose.add_argument("--run-id", required=True)
    p_compose.add_argument("--host", required=True)
    p_compose.add_argument("--role", default="")
    p_compose.add_argument("--systemd-units-json", type=Path, required=True)
    p_compose.add_argument("--docker-containers-json", type=Path, required=True)
    p_compose.add_argument("--managed-files-json", type=Path, required=True)
    p_compose.add_argument("--receipts-dir", type=Path, default=DEFAULT_RECEIPTS_DIR)
    p_compose.set_defaults(func=_cmd_compose)

    p_inspect = sub.add_parser("inspect", help="Pretty-print snapshot summaries")
    p_inspect.add_argument("--path", type=Path)
    p_inspect.add_argument("--host")
    p_inspect.add_argument("--receipts-dir", type=Path, default=DEFAULT_RECEIPTS_DIR)
    p_inspect.set_defaults(func=_cmd_inspect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
