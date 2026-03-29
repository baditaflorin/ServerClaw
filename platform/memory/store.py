from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from platform.world_state._db import (
    ConnectionFactory,
    connection_kind,
    create_connection_factory,
    decode_json,
    isoformat,
    managed_connection,
    parse_timestamp,
    placeholder,
    rows_to_dicts,
    utc_now,
)


DEFAULT_POSTGRES_TABLE = "memory.entries"
DEFAULT_SQLITE_TABLE = "memory_entries"


@dataclass(frozen=True)
class MemoryEntry:
    memory_id: str
    scope_kind: str
    scope_id: str
    object_type: str
    title: str
    content: str
    provenance: str
    retention_class: str
    consent_boundary: str
    delegation_boundary: str | None
    source_uri: str | None
    metadata: dict[str, Any]
    last_refreshed_at: datetime
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "scope_kind": self.scope_kind,
            "scope_id": self.scope_id,
            "object_type": self.object_type,
            "title": self.title,
            "content": self.content,
            "provenance": self.provenance,
            "retention_class": self.retention_class,
            "consent_boundary": self.consent_boundary,
            "delegation_boundary": self.delegation_boundary,
            "source_uri": self.source_uri,
            "metadata": self.metadata,
            "last_refreshed_at": isoformat(self.last_refreshed_at),
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
            "expires_at": isoformat(self.expires_at) if self.expires_at is not None else None,
        }


@dataclass(frozen=True)
class MemoryEntryInput:
    scope_kind: str
    scope_id: str
    object_type: str
    title: str
    content: str
    provenance: str
    retention_class: str
    consent_boundary: str
    delegation_boundary: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] | None = None
    last_refreshed_at: datetime | None = None
    expires_at: datetime | None = None
    memory_id: str | None = None


class MemoryStore:
    def __init__(
        self,
        *,
        dsn: str,
        connection_factory: ConnectionFactory | None = None,
        postgres_table_name: str = DEFAULT_POSTGRES_TABLE,
        sqlite_table_name: str = DEFAULT_SQLITE_TABLE,
    ) -> None:
        self._dsn = dsn
        self._connection_factory = connection_factory
        self._postgres_table_name = postgres_table_name
        self._sqlite_table_name = sqlite_table_name

    def ensure_sqlite_schema(self) -> None:
        with managed_connection(self._resolved_connection_factory()) as connection:
            if connection_kind(connection) != "sqlite":
                return
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._sqlite_table_name} (
                    memory_id TEXT PRIMARY KEY,
                    scope_kind TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    retention_class TEXT NOT NULL,
                    consent_boundary TEXT NOT NULL,
                    delegation_boundary TEXT,
                    source_uri TEXT,
                    metadata TEXT NOT NULL DEFAULT '{{}}',
                    last_refreshed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT
                )
                """
            )
            connection.commit()

    def upsert(self, payload: MemoryEntryInput) -> MemoryEntry:
        with managed_connection(self._resolved_connection_factory()) as connection:
            memory_id = (payload.memory_id or str(uuid.uuid4())).strip()
            now = utc_now()
            last_refreshed_at = payload.last_refreshed_at or now
            metadata = payload.metadata or {}
            table_name = self._resolved_table_name(connection)
            parameter = placeholder(connection)
            metadata_value = json.dumps(metadata, sort_keys=True)
            created_at = self._existing_created_at(connection, memory_id) or now
            connection.execute(
                f"""
                INSERT INTO {table_name} (
                    memory_id,
                    scope_kind,
                    scope_id,
                    object_type,
                    title,
                    content,
                    provenance,
                    retention_class,
                    consent_boundary,
                    delegation_boundary,
                    source_uri,
                    metadata,
                    last_refreshed_at,
                    created_at,
                    updated_at,
                    expires_at
                ) VALUES (
                    {parameter}, {parameter}, {parameter}, {parameter}, {parameter}, {parameter},
                    {parameter}, {parameter}, {parameter}, {parameter}, {parameter}, {parameter},
                    {parameter}, {parameter}, {parameter}, {parameter}
                )
                ON CONFLICT(memory_id) DO UPDATE SET
                    scope_kind = excluded.scope_kind,
                    scope_id = excluded.scope_id,
                    object_type = excluded.object_type,
                    title = excluded.title,
                    content = excluded.content,
                    provenance = excluded.provenance,
                    retention_class = excluded.retention_class,
                    consent_boundary = excluded.consent_boundary,
                    delegation_boundary = excluded.delegation_boundary,
                    source_uri = excluded.source_uri,
                    metadata = excluded.metadata,
                    last_refreshed_at = excluded.last_refreshed_at,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (
                    memory_id,
                    payload.scope_kind,
                    payload.scope_id,
                    payload.object_type,
                    payload.title,
                    payload.content,
                    payload.provenance,
                    payload.retention_class,
                    payload.consent_boundary,
                    payload.delegation_boundary,
                    payload.source_uri,
                    metadata_value,
                    isoformat(last_refreshed_at),
                    isoformat(created_at),
                    isoformat(now),
                    isoformat(payload.expires_at) if payload.expires_at is not None else None,
                ),
            )
            connection.commit()
            entry = self.get(memory_id)
            if entry is None:  # pragma: no cover - defensive guard
                raise RuntimeError(f"memory entry disappeared after write: {memory_id}")
            return entry

    def get(self, memory_id: str) -> MemoryEntry | None:
        with managed_connection(self._resolved_connection_factory()) as connection:
            table_name = self._resolved_table_name(connection)
            parameter = placeholder(connection)
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT * FROM {table_name}
                WHERE memory_id = {parameter}
                  AND (expires_at IS NULL OR expires_at > {parameter})
                """,
                (memory_id, isoformat(utc_now())),
            )
            rows = rows_to_dicts(cursor)
        if not rows:
            return None
        return self._row_to_entry(rows[0])

    def delete(self, memory_id: str) -> bool:
        with managed_connection(self._resolved_connection_factory()) as connection:
            table_name = self._resolved_table_name(connection)
            parameter = placeholder(connection)
            cursor = connection.cursor()
            cursor.execute(
                f"DELETE FROM {table_name} WHERE memory_id = {parameter}",
                (memory_id,),
            )
            deleted = cursor.rowcount > 0
            connection.commit()
        return deleted

    def list_entries(
        self,
        *,
        scope_kind: str,
        scope_id: str,
        object_type: str | None = None,
        memory_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        with managed_connection(self._resolved_connection_factory()) as connection:
            table_name = self._resolved_table_name(connection)
            parameter = placeholder(connection)
            conditions = [
                f"scope_kind = {parameter}",
                f"scope_id = {parameter}",
                f"(expires_at IS NULL OR expires_at > {parameter})",
            ]
            values: list[Any] = [scope_kind, scope_id, isoformat(utc_now())]
            if object_type:
                conditions.append(f"object_type = {parameter}")
                values.append(object_type)
            if memory_ids:
                placeholders = ", ".join([parameter] * len(memory_ids))
                conditions.append(f"memory_id IN ({placeholders})")
                values.extend(memory_ids)
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT * FROM {table_name}
                WHERE {' AND '.join(conditions)}
                ORDER BY last_refreshed_at DESC, updated_at DESC, memory_id ASC
                LIMIT {int(limit)}
                """,
                tuple(values),
            )
            rows = rows_to_dicts(cursor)
        return [self._row_to_entry(row) for row in rows]

    def all_active_entries(self) -> list[MemoryEntry]:
        with managed_connection(self._resolved_connection_factory()) as connection:
            table_name = self._resolved_table_name(connection)
            parameter = placeholder(connection)
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT * FROM {table_name}
                WHERE expires_at IS NULL OR expires_at > {parameter}
                ORDER BY scope_kind ASC, scope_id ASC, last_refreshed_at DESC, memory_id ASC
                """,
                (isoformat(utc_now()),),
            )
            rows = rows_to_dicts(cursor)
        return [self._row_to_entry(row) for row in rows]

    def _existing_created_at(self, connection: Any, memory_id: str) -> datetime | None:
        table_name = self._resolved_table_name(connection)
        parameter = placeholder(connection)
        cursor = connection.cursor()
        cursor.execute(
            f"SELECT created_at FROM {table_name} WHERE memory_id = {parameter}",
            (memory_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        value = row[0] if not isinstance(row, dict) else row.get("created_at")
        return parse_timestamp(value)

    def _resolved_connection_factory(self) -> ConnectionFactory:
        return self._connection_factory or create_connection_factory(self._dsn)

    def _resolved_table_name(self, connection: Any) -> str:
        return self._sqlite_table_name if connection_kind(connection) == "sqlite" else self._postgres_table_name

    def _row_to_entry(self, row: dict[str, Any]) -> MemoryEntry:
        return MemoryEntry(
            memory_id=str(row["memory_id"]),
            scope_kind=str(row["scope_kind"]),
            scope_id=str(row["scope_id"]),
            object_type=str(row["object_type"]),
            title=str(row["title"]),
            content=str(row["content"]),
            provenance=str(row["provenance"]),
            retention_class=str(row["retention_class"]),
            consent_boundary=str(row["consent_boundary"]),
            delegation_boundary=(str(row["delegation_boundary"]) if row.get("delegation_boundary") is not None else None),
            source_uri=(str(row["source_uri"]) if row.get("source_uri") is not None else None),
            metadata=decode_json(row.get("metadata") or "{}") or {},
            last_refreshed_at=parse_timestamp(row["last_refreshed_at"]),
            created_at=parse_timestamp(row["created_at"]),
            updated_at=parse_timestamp(row["updated_at"]),
            expires_at=parse_timestamp(row["expires_at"]) if row.get("expires_at") is not None else None,
        )
