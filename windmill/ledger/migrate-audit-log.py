from __future__ import annotations

import argparse
import json
from typing import Any, Callable

from platform.ledger.writer import LedgerWriter, derive_target_kind, mutation_audit_event_type


LEGACY_VIEW_SQL = """
CREATE OR REPLACE VIEW audit_log AS
SELECT
    id,
    occurred_at AS ts,
    split_part(actor, ':', 1) AS actor_class,
    CASE
        WHEN position(':' in actor) > 0 THEN substring(actor FROM position(':' in actor) + 1)
        ELSE actor
    END AS actor_id,
    COALESCE(metadata->>'legacy_surface', tool_id, 'manual') AS surface,
    COALESCE(metadata->>'legacy_action', event_type) AS action,
    target_id AS target,
    CASE
        WHEN event_type = 'execution.completed' THEN 'success'
        WHEN event_type = 'execution.failed' THEN 'failure'
        WHEN event_type = 'execution.aborted' THEN 'rejected'
        ELSE 'success'
    END AS outcome,
    COALESCE(metadata->>'legacy_correlation_id', event_id::text) AS correlation_id,
    COALESCE(metadata->>'legacy_evidence_ref', '') AS evidence_ref
FROM ledger.events;
""".strip()


def _normalize_actor(row: dict[str, Any]) -> tuple[str, str]:
    actor = row.get("actor")
    if isinstance(actor, dict):
        actor_class = str(actor.get("class") or "").strip()
        actor_id = str(actor.get("id") or "").strip()
        if actor_class and actor_id:
            return actor_class, actor_id
    actor_class = str(row.get("actor_class") or "automation").strip()
    actor_id = str(row.get("actor_id") or "legacy-audit-log").strip()
    return actor_class, actor_id


def map_audit_row(row: dict[str, Any]) -> dict[str, Any]:
    actor_class, actor_id = _normalize_actor(row)
    surface = str(row.get("surface") or "manual").strip()
    action = str(row.get("action") or "legacy.audit_log").strip()
    target = str(row.get("target") or "unknown-target").strip()
    ts = row.get("ts") or row.get("occurred_at")
    return {
        "event_type": mutation_audit_event_type({"outcome": row.get("outcome", "success")}),
        "occurred_at": ts,
        "actor": f"{actor_class}:{actor_id}",
        "tool_id": surface or None,
        "target_kind": derive_target_kind(surface=surface, action=action, target=target),
        "target_id": target,
        "before_state": None,
        "after_state": None,
        "receipt": None,
        "metadata": {
            "legacy_event": True,
            "legacy_surface": surface,
            "legacy_action": action,
            "legacy_outcome": row.get("outcome"),
            "legacy_correlation_id": row.get("correlation_id"),
            "legacy_evidence_ref": row.get("evidence_ref"),
            "legacy_row_id": row.get("id"),
            "state_capture": False,
        },
    }


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {column[0]: value for column, value in zip(cursor.description or [], row, strict=False)}


def _audit_log_source_exists(connection: Any) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.audit_log') IS NOT NULL")
        row = cursor.fetchone()
    if isinstance(row, dict):
        return bool(next(iter(row.values()), False))
    if isinstance(row, tuple):
        return bool(row[0]) if row else False
    return bool(row)


def migrate_audit_log(
    *,
    dsn: str | None = None,
    connection: Any = None,
    connect: Callable[[str], Any] | None = None,
    batch_size: int = 500,
    replace_legacy_table: bool = True,
) -> dict[str, Any]:
    writer = LedgerWriter(dsn=dsn, connection=connection, connect=connect, nats_publisher=None)
    source_connection = connection
    if source_connection is None:
        if connect is None:
            raise RuntimeError("migrate_audit_log requires either connection or connect")
        if not dsn:
            raise RuntimeError("migrate_audit_log requires dsn when opening its own connection")
        source_connection = connect(dsn)

    migrated = 0
    batch_count = 0
    view_applied = False
    if _audit_log_source_exists(source_connection):
        with source_connection.cursor() as cursor:
            cursor.execute("SELECT * FROM audit_log ORDER BY id ASC")
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                batch_count += 1
                for row in rows:
                    writer.write(**map_audit_row(_row_to_dict(cursor, row)))
                    migrated += 1

    if replace_legacy_table:
        with source_connection.cursor() as cursor:
            cursor.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'audit_log'
                    ) THEN
                        EXECUTE 'ALTER TABLE audit_log RENAME TO audit_log_legacy';
                    END IF;
                END;
                $$;
                """
            )
            cursor.execute(LEGACY_VIEW_SQL)
        source_connection.commit()
        view_applied = True

    return {
        "migrated_rows": migrated,
        "batches": batch_count,
        "legacy_view_applied": view_applied,
    }


def main(
    dsn: str = "",
    batch_size: int = 500,
    replace_legacy_table: bool = True,
) -> dict[str, Any]:
    def connect(resolved_dsn: str):
        import psycopg2  # type: ignore

        return psycopg2.connect(resolved_dsn)

    return migrate_audit_log(
        dsn=dsn or None,
        connect=connect,
        batch_size=batch_size,
        replace_legacy_table=replace_legacy_table,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate legacy audit_log rows into ledger.events.")
    parser.add_argument("--dsn", help="Postgres connection string.", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--preserve-legacy-table",
        action="store_true",
        help="Do not rename the old audit_log table or install the compatibility view.",
    )
    args = parser.parse_args()
    result = main(
        dsn=args.dsn,
        batch_size=args.batch_size,
        replace_legacy_table=not args.preserve_legacy_table,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
