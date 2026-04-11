#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, repo_path
from data_catalog import load_data_catalog, validate_data_catalog
from mutation_audit import DEFAULT_LOCAL_SINK_PATH


DEFAULT_RECEIPTS_ROOT = repo_path("receipts")
DEFAULT_CATALOG_PATH = repo_path("config", "data-catalog.json")
AUDIT_STORE_ID = "mutation-audit-log"


@dataclass(frozen=True)
class PurgeTarget:
    store_id: str
    root: Path
    retention_days: int


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def cutoff_for_days(retention_days: int, now: dt.datetime) -> dt.datetime:
    return now - dt.timedelta(days=retention_days)


def load_purge_targets(catalog_path: Path, receipts_root: Path) -> list[PurgeTarget]:
    catalog = load_data_catalog(catalog_path)
    validate_data_catalog(catalog)
    targets: list[PurgeTarget] = []
    for store in catalog["data_stores"]:
        retention_days = store.get("retention_days")
        retention_paths = store.get("retention_paths") or []
        if retention_days is None:
            continue
        for relative_path in retention_paths:
            targets.append(
                PurgeTarget(
                    store_id=store["id"],
                    root=receipts_root / relative_path,
                    retention_days=retention_days,
                )
            )
    return targets


def should_skip_file(path: Path) -> bool:
    return path.name in {".gitkeep", ".gitignore"}


def purge_directory(target: PurgeTarget, now: dt.datetime, execute: bool) -> dict[str, Any]:
    cutoff = cutoff_for_days(target.retention_days, now)
    removed: list[str] = []
    skipped: list[str] = []

    if not target.root.exists():
        return {
            "store_id": target.store_id,
            "path": str(target.root),
            "exists": False,
            "retention_days": target.retention_days,
            "removed": [],
            "skipped": [],
        }

    for candidate in sorted(target.root.rglob("*")):
        if not candidate.is_file() or should_skip_file(candidate):
            continue
        modified_at = dt.datetime.fromtimestamp(candidate.stat().st_mtime, tz=dt.UTC)
        relative = str(candidate.relative_to(target.root.parent))
        if modified_at >= cutoff:
            skipped.append(relative)
            continue
        removed.append(relative)
        if execute:
            candidate.unlink()

    return {
        "store_id": target.store_id,
        "path": str(target.root),
        "exists": True,
        "retention_days": target.retention_days,
        "removed": removed,
        "skipped": skipped,
    }


def _parse_event_ts(raw_line: str) -> dt.datetime | None:
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    raw_ts = payload.get("ts")
    if not isinstance(raw_ts, str) or not raw_ts.strip():
        return None
    return dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))


def purge_audit_log(
    audit_log_path: Path, retention_days: int | None, now: dt.datetime, execute: bool
) -> dict[str, Any]:
    if retention_days is None:
        return {
            "store_id": AUDIT_STORE_ID,
            "path": str(audit_log_path),
            "exists": audit_log_path.exists(),
            "retention_days": None,
            "removed_lines": 0,
            "kept_lines": 0,
            "invalid_lines": 0,
        }

    if not audit_log_path.exists():
        return {
            "store_id": AUDIT_STORE_ID,
            "path": str(audit_log_path),
            "exists": False,
            "retention_days": retention_days,
            "removed_lines": 0,
            "kept_lines": 0,
            "invalid_lines": 0,
        }

    cutoff = cutoff_for_days(retention_days, now)
    kept_lines: list[str] = []
    removed_lines = 0
    invalid_lines = 0
    for raw_line in audit_log_path.read_text(encoding="utf-8").splitlines():
        parsed_ts = _parse_event_ts(raw_line)
        if parsed_ts is None:
            kept_lines.append(raw_line)
            invalid_lines += 1
            continue
        if parsed_ts < cutoff:
            removed_lines += 1
            continue
        kept_lines.append(raw_line)

    if execute:
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        audit_log_path.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")

    return {
        "store_id": AUDIT_STORE_ID,
        "path": str(audit_log_path),
        "exists": True,
        "retention_days": retention_days,
        "removed_lines": removed_lines,
        "kept_lines": len(kept_lines),
        "invalid_lines": invalid_lines,
    }


def audit_retention_days(catalog_path: Path) -> int | None:
    catalog = load_data_catalog(catalog_path)
    validate_data_catalog(catalog)
    for store in catalog["data_stores"]:
        if store["id"] == AUDIT_STORE_ID:
            return store.get("retention_days")
    return None


def run_purge(
    *,
    catalog_path: Path,
    receipts_root: Path,
    audit_log_path: Path,
    execute: bool,
) -> dict[str, Any]:
    now = utc_now()
    receipt_results = [
        purge_directory(target, now, execute) for target in load_purge_targets(catalog_path, receipts_root)
    ]
    audit_result = purge_audit_log(
        audit_log_path,
        audit_retention_days(catalog_path),
        now,
        execute,
    )
    return {
        "executed": execute,
        "run_at": now.isoformat().replace("+00:00", "Z"),
        "receipts_root": str(receipts_root),
        "audit_log_path": str(audit_log_path),
        "receipt_targets": receipt_results,
        "audit_log_target": audit_result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Purge expired receipt files and mutation-audit entries.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH, help="Path to config/data-catalog.json.")
    parser.add_argument(
        "--receipts-root",
        type=Path,
        default=DEFAULT_RECEIPTS_ROOT,
        help="Root directory containing receipt subdirectories.",
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=DEFAULT_LOCAL_SINK_PATH,
        help="Path to the mutation audit JSONL sink.",
    )
    parser.add_argument("--execute", action="store_true", help="Delete expired data instead of only reporting it.")
    args = parser.parse_args(argv)

    try:
        payload = run_purge(
            catalog_path=args.catalog,
            receipts_root=args.receipts_root,
            audit_log_path=args.audit_log,
            execute=args.execute,
        )
    except (OSError, ValueError) as exc:
        return emit_cli_error("Receipt retention", exc)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
