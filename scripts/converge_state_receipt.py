#!/usr/bin/env python3
"""Compute and persist before/after converge-state diffs.

ADR 0466 — half-applied converge detection. After a converge the
operator wants to know:

  - Which managed files actually changed?
  - Which systemd handlers fired and which were notified-but-skipped?
  - Did anything get left in a half-applied state?

Today, Ansible's `changed: true` per-task signal tells you the role
*intended* a change but does not tell you whether the resulting file
matches the template's idempotent output. The 2026-04-28
nginx-buffer-not-reloaded incident is the canonical case: the
template was rewritten but the handler that reloads nginx didn't
fire (or did fire but failed silently), and there was no
post-converge artifact to grep against.

This script writes per-converge state receipts to
`receipts/converge-state/<run_id>.json`, computed from a list of
managed file paths the role hands in. The shape:

```json
{
  "schema_version": "1.0.0",
  "run_id": "<run_id>",
  "host": "<inventory_hostname>",
  "role": "<role_name>",
  "recorded_at": "<UTC iso>",
  "files": [
    {
      "path": "/etc/nginx/sites-available/lv3-edge.conf",
      "before_sha256": "...",
      "after_sha256": "...",
      "changed": true,
      "size_bytes_before": 1234,
      "size_bytes_after": 1240
    }
  ],
  "handlers_fired": ["reload nginx"],
  "handlers_notified_but_skipped": []
}
```

Two CLI modes:

  - `snapshot` — given a list of paths, emit a JSON array of
    `{path, sha256, size_bytes}` to stdout. Roles call this twice
    (before+after) and pipe the output into receipt-write.
  - `write-receipt` — given a run_id, host, role, before/after JSON
    snapshots, handlers-fired list, and handlers-notified list,
    compute the diff and write the receipt atomically.

The receipts are read by a future `make doctor` signal that flags
roles whose last-receipt timestamp is older than the role's managed
file mtimes — an out-of-scope follow-up; ws-0468 only ships the leaf
primitive.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPTS_DIR = REPO_ROOT / "receipts" / "converge-state"


def file_snapshot(path: Path) -> dict:
    """Return {path, sha256, size_bytes} or {path, missing: true}."""
    if not path.is_file():
        return {"path": str(path), "missing": True}
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
            size += len(chunk)
    return {"path": str(path), "sha256": h.hexdigest(), "size_bytes": size}


def diff_snapshots(before: list[dict], after: list[dict]) -> list[dict]:
    """Pairwise diff. Index by path so the order doesn't matter."""
    bmap = {entry["path"]: entry for entry in before}
    amap = {entry["path"]: entry for entry in after}
    paths = sorted(set(bmap) | set(amap))
    out: list[dict] = []
    for path in paths:
        b = bmap.get(path, {"path": path, "missing": True})
        a = amap.get(path, {"path": path, "missing": True})
        b_sha = b.get("sha256")
        a_sha = a.get("sha256")
        b_missing = b.get("missing", False)
        a_missing = a.get("missing", False)
        out.append(
            {
                "path": path,
                "before_sha256": b_sha,
                "after_sha256": a_sha,
                "before_missing": b_missing,
                "after_missing": a_missing,
                "changed": (b_sha != a_sha) or (b_missing != a_missing),
                "size_bytes_before": b.get("size_bytes"),
                "size_bytes_after": a.get("size_bytes"),
            }
        )
    return out


def write_state_receipt(
    receipts_dir: Path,
    *,
    run_id: str,
    host: str,
    role: str,
    files: list[dict],
    handlers_fired: list[str],
    handlers_notified_but_skipped: list[str],
) -> Path:
    """Atomic write per ADR 0461."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from check_receipt_freshness import write_receipt_atomic

    now = dt.datetime.now(dt.UTC)
    safe_run = run_id.replace("/", "_").replace("\\", "_")[:64]
    path = receipts_dir / f"{safe_run}.json"
    payload = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "host": host,
        "role": role,
        "recorded_at": now.isoformat(timespec="seconds"),
        "files": files,
        "handlers_fired": list(handlers_fired),
        "handlers_notified_but_skipped": list(handlers_notified_but_skipped),
        "summary": {
            "files_total": len(files),
            "files_changed": sum(1 for f in files if f.get("changed")),
            "handlers_fired": len(handlers_fired),
            "handlers_skipped": len(handlers_notified_but_skipped),
        },
    }
    write_receipt_atomic(path, payload)
    return path


def _cmd_snapshot(args: argparse.Namespace) -> int:
    snapshots = [file_snapshot(Path(p)) for p in args.paths]
    print(json.dumps(snapshots, indent=2, sort_keys=True))
    return 0


def _cmd_write_receipt(args: argparse.Namespace) -> int:
    before = json.loads(Path(args.before).read_text())
    after = json.loads(Path(args.after).read_text())
    if not isinstance(before, list) or not isinstance(after, list):
        print("write-receipt: --before and --after must contain JSON arrays", file=sys.stderr)
        return 2
    files = diff_snapshots(before, after)
    handlers_fired = (args.handlers_fired or "").split(",") if args.handlers_fired else []
    handlers_skipped = (args.handlers_notified_but_skipped or "").split(",") if args.handlers_notified_but_skipped else []
    receipt_path = write_state_receipt(
        args.receipts_dir,
        run_id=args.run_id,
        host=args.host,
        role=args.role,
        files=files,
        handlers_fired=[h.strip() for h in handlers_fired if h.strip()],
        handlers_notified_but_skipped=[h.strip() for h in handlers_skipped if h.strip()],
    )
    try:
        print(str(receipt_path.relative_to(REPO_ROOT)))
    except ValueError:
        print(str(receipt_path))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="converge_state_receipt", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="Emit JSON array of {path, sha256, size_bytes} for given paths")
    p_snap.add_argument("paths", nargs="+", help="File paths to snapshot")
    p_snap.set_defaults(func=_cmd_snapshot)

    p_write = sub.add_parser("write-receipt", help="Diff before/after snapshots and write a converge-state receipt")
    p_write.add_argument("--run-id", required=True)
    p_write.add_argument("--host", required=True)
    p_write.add_argument("--role", required=True)
    p_write.add_argument("--before", type=Path, required=True, help="Path to before snapshot JSON")
    p_write.add_argument("--after", type=Path, required=True, help="Path to after snapshot JSON")
    p_write.add_argument("--handlers-fired", default="", help="Comma-separated handler names that fired")
    p_write.add_argument("--handlers-notified-but-skipped", default="")
    p_write.add_argument("--receipts-dir", type=Path, default=DEFAULT_RECEIPTS_DIR)
    p_write.set_defaults(func=_cmd_write_receipt)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
