from __future__ import annotations

from typing import Any, Callable

from ._common import normalize_event_row, normalize_timestamp, resolve_connection


class LedgerReader:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        connection: Any = None,
        connect: Callable[[str], Any] | None = None,
    ) -> None:
        self._dsn = dsn
        self._connection = connection
        self._connect = connect

    def _fetch_all(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        connection, owned_connection = resolve_connection(
            dsn=self._dsn,
            connection=self._connection,
            connect=self._connect,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [normalize_event_row(cursor, row) for row in rows]
        finally:
            if owned_connection:
                connection.close()

    def events_by_target(
        self,
        *,
        target_kind: str,
        target_id: str,
        from_ts: str | None = None,
        to_ts: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["target_kind = %s", "target_id = %s"]
        params: list[Any] = [target_kind, target_id]
        if from_ts:
            clauses.append("occurred_at >= %s")
            params.append(normalize_timestamp(from_ts))
        if to_ts:
            clauses.append("occurred_at <= %s")
            params.append(normalize_timestamp(to_ts))
        params.append(limit)
        return self._fetch_all(
            f"""
            SELECT
                id,
                event_id,
                event_type,
                occurred_at,
                actor,
                actor_intent_id,
                tool_id,
                target_kind,
                target_id,
                before_state,
                after_state,
                receipt,
                metadata
            FROM ledger.events
            WHERE {' AND '.join(clauses)}
            ORDER BY occurred_at ASC, id ASC
            LIMIT %s
            """,
            tuple(params),
        )

    def events_by_intent(self, actor_intent_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT
                id,
                event_id,
                event_type,
                occurred_at,
                actor,
                actor_intent_id,
                tool_id,
                target_kind,
                target_id,
                before_state,
                after_state,
                receipt,
                metadata
            FROM ledger.events
            WHERE actor_intent_id = %s
            ORDER BY occurred_at ASC, id ASC
            LIMIT %s
            """,
            (actor_intent_id, limit),
        )

    def events_in_time_range(
        self,
        *,
        from_ts: str,
        to_ts: str,
        limit: int = 1000,
        target_kind: str | None = None,
        target_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["occurred_at >= %s", "occurred_at <= %s"]
        params: list[Any] = [normalize_timestamp(from_ts), normalize_timestamp(to_ts)]
        if target_kind:
            clauses.append("target_kind = %s")
            params.append(target_kind)
        if target_id:
            clauses.append("target_id = %s")
            params.append(target_id)
        params.append(limit)
        return self._fetch_all(
            f"""
            SELECT
                id,
                event_id,
                event_type,
                occurred_at,
                actor,
                actor_intent_id,
                tool_id,
                target_kind,
                target_id,
                before_state,
                after_state,
                receipt,
                metadata
            FROM ledger.events
            WHERE {' AND '.join(clauses)}
            ORDER BY occurred_at ASC, id ASC
            LIMIT %s
            """,
            tuple(params),
        )
