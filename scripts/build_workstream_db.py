#!/usr/bin/env python3
"""Build a SQLite index of the workstream registry — ADR 0473 phase 11.2.

Reads `workstreams.yaml` (2.7 MB) and writes `build/workstreams.sqlite3`
with one indexed row per workstream. Agents querying "what's in flight
for service X" or "which workstreams depend on ADR 0470" run a 50 ms
SQL query instead of parsing the full YAML.

Schema:
  workstreams(
    id              TEXT PRIMARY KEY,
    adr             TEXT,
    title           TEXT,
    status          TEXT,
    ready_to_merge  INTEGER,
    live_applied    INTEGER,
    owner           TEXT,
    branch          TEXT,
    worktree_path   TEXT,
    doc             TEXT,
    plane_issue_id  TEXT
  )

Indexes on adr, status, owner — the dimensions agents filter on most.

Usage:
  python scripts/build_workstream_db.py --write
  python scripts/build_workstream_db.py --check    # exit 1 if stale vs HEAD
  python scripts/build_workstream_db.py --query "SELECT id, status FROM workstreams WHERE owner='claude'"

Exit:
  0  wrote (or check passed, or query returned)
  1  --check reported drift
  2  invocation error
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSTREAMS_PATH = REPO_ROOT / "workstreams.yaml"
DB_PATH = REPO_ROOT / "build" / "workstreams.sqlite3"


COLUMNS: tuple[tuple[str, str], ...] = (
    ("id", "TEXT PRIMARY KEY"),
    ("adr", "TEXT"),
    ("title", "TEXT"),
    ("status", "TEXT"),
    ("ready_to_merge", "INTEGER"),
    ("live_applied", "INTEGER"),
    ("owner", "TEXT"),
    ("branch", "TEXT"),
    ("worktree_path", "TEXT"),
    ("doc", "TEXT"),
    ("plane_issue_id", "TEXT"),
)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def normalise(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "adr": str(entry.get("adr")) if entry.get("adr") is not None else None,
        "title": entry.get("title"),
        "status": entry.get("status"),
        "ready_to_merge": _to_int(entry.get("ready_to_merge")),
        "live_applied": _to_int(entry.get("live_applied")),
        "owner": entry.get("owner"),
        "branch": entry.get("branch"),
        "worktree_path": entry.get("worktree_path"),
        "doc": entry.get("doc"),
        "plane_issue_id": entry.get("plane_issue_id"),
    }


def load_workstreams(path: Path = WORKSTREAMS_PATH) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = payload.get("workstreams") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    return [normalise(item) for item in raw if isinstance(item, dict) and item.get("id")]


def workstreams_fingerprint(path: Path = WORKSTREAMS_PATH) -> str:
    """Cheap content fingerprint used by `--check`."""
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_db(rows: list[dict[str, Any]], db_path: Path, *, source_path: Path = WORKSTREAMS_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        column_defs = ", ".join(f"{name} {ddl}" for name, ddl in COLUMNS)
        cur.execute(f"CREATE TABLE workstreams ({column_defs})")
        cur.execute("CREATE INDEX idx_workstreams_status ON workstreams(status)")
        cur.execute("CREATE INDEX idx_workstreams_adr    ON workstreams(adr)")
        cur.execute("CREATE INDEX idx_workstreams_owner  ON workstreams(owner)")
        cur.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
        placeholders = ", ".join("?" for _ in COLUMNS)
        column_names = ", ".join(name for name, _ in COLUMNS)
        cur.executemany(
            f"INSERT INTO workstreams ({column_names}) VALUES ({placeholders})",
            [tuple(row[name] for name, _ in COLUMNS) for row in rows],
        )
        cur.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            ("workstreams_yaml_sha256", workstreams_fingerprint(source_path)),
        )
        conn.commit()
    finally:
        conn.close()


def db_fingerprint(db_path: Path) -> str | None:
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key=?", ("workstreams_yaml_sha256",))
        row = cur.fetchone()
        return row[0] if row else None
    except sqlite3.DatabaseError:
        return None
    finally:
        conn.close()


def write(*, db_path: Path = DB_PATH, workstreams_path: Path = WORKSTREAMS_PATH) -> int:
    rows = load_workstreams(workstreams_path)
    build_db(rows, db_path, source_path=workstreams_path)
    print(f"build_workstream_db: wrote {len(rows)} rows to {db_path.as_posix()}", file=sys.stderr)
    return 0


def check(*, db_path: Path = DB_PATH, workstreams_path: Path = WORKSTREAMS_PATH) -> int:
    expected = workstreams_fingerprint(workstreams_path)
    actual = db_fingerprint(db_path)
    if expected != actual:
        print(
            f"build_workstream_db: stale — {db_path.as_posix()} fingerprint {actual} != workstreams.yaml {expected}",
            file=sys.stderr,
        )
        return 1
    return 0


def query(sql: str, db_path: Path = DB_PATH) -> int:
    if not db_path.is_file():
        print(f"build_workstream_db: db missing at {db_path.as_posix()} — run --write first", file=sys.stderr)
        return 2
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if not rows:
            print("(no rows)")
            return 0
        keys = list(rows[0].keys())
        print("\t".join(keys))
        for row in rows:
            print("\t".join("" if row[k] is None else str(row[k]) for k in keys))
        return 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--workstreams-path", default=str(WORKSTREAMS_PATH))
    parser.add_argument("--db-path", default=str(DB_PATH))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="(Re)build the SQLite index.")
    group.add_argument("--check", action="store_true", help="Verify db is current vs workstreams.yaml.")
    group.add_argument("--query", help="Run a SELECT against the db; prints TSV.")
    args = parser.parse_args(argv)

    db_path = Path(args.db_path)
    ws_path = Path(args.workstreams_path)

    if args.write:
        return write(db_path=db_path, workstreams_path=ws_path)
    if args.check:
        return check(db_path=db_path, workstreams_path=ws_path)
    return query(args.query, db_path=db_path)


if __name__ == "__main__":
    sys.exit(main())
