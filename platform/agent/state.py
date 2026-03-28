from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from platform.events.publisher import publish_nats_events
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


def _default_checkpoint_publisher(subject: str, payload: dict[str, Any]) -> None:
    nats_url = os.environ.get("LV3_AGENT_STATE_NATS_URL", "").strip() or os.environ.get("LV3_NATS_URL", "").strip()
    if not nats_url:
        return
    publish_nats_events(  # pragma: no cover - network side effect
        [{"subject": subject, "payload": payload}],
        nats_url=nats_url,
        credentials=None,
    )


def _publish_async(
    publisher: Callable[[str, dict[str, Any]], None] | None,
    subject: str,
    payload: dict[str, Any],
) -> None:
    if publisher is None:
        return

    def runner() -> None:
        try:
            publisher(subject, payload)
        except Exception:
            return

    thread = threading.Thread(target=runner, name="agent-state-checkpoint-publisher", daemon=True)
    thread.start()


class AgentStateError(RuntimeError):
    pass


class AgentStateConflictError(AgentStateError):
    def __init__(self, agent_id: str, task_id: str, key: str):
        super().__init__(f"agent state conflict for {agent_id}/{task_id}/{key}")
        self.agent_id = agent_id
        self.task_id = task_id
        self.key = key


class AgentStateLimitError(AgentStateError):
    pass


@dataclass(frozen=True)
class StateEntry:
    key: str
    value: Any
    written_at: datetime
    expires_at: datetime
    version: int
    context_id: str | None


@dataclass(frozen=True)
class IntegrityValidationResult:
    agent_id: str
    task_id: str
    expected_digest: str
    actual_digest: str
    matched: bool
    key_count: int


class AgentStateClient:
    def __init__(
        self,
        agent_id: str,
        task_id: str,
        default_ttl_hours: int = 24,
        *,
        context_id: str | None = None,
        dsn: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        table_name: str | None = None,
        max_value_bytes: int = 64 * 1024,
        max_keys: int = 100,
        now: Callable[[], datetime] = utc_now,
        checkpoint_publisher: Callable[[str, dict[str, Any]], None] | None = _default_checkpoint_publisher,
        checkpoint_subject: str = "platform.agent.state_checkpoint",
    ) -> None:
        self.agent_id = agent_id.strip()
        self.task_id = task_id.strip()
        if not self.agent_id:
            raise ValueError("agent_id must be a non-empty string")
        if not self.task_id:
            raise ValueError("task_id must be a non-empty string")
        if default_ttl_hours <= 0:
            raise ValueError("default_ttl_hours must be positive")
        self.default_ttl_hours = default_ttl_hours
        self.context_id = context_id or os.environ.get("LV3_CONTEXT_ID", "").strip() or None
        self._dsn = dsn
        self._connection_factory = connection_factory
        self._table_name = table_name
        self.max_value_bytes = max_value_bytes
        self.max_keys = max_keys
        self._now = now
        self._checkpoint_publisher = checkpoint_publisher
        self._checkpoint_subject = checkpoint_subject
        self._version_cache: dict[str, int] = {}

    def write(self, key: str, value: Any, ttl_hours: int | float | None = None) -> None:
        with managed_connection(self._resolved_connection_factory()) as connection:
            self._write_with_connection(connection, key, value, ttl_hours=ttl_hours)
            connection.commit()

    def read(self, key: str, default: Any = None) -> Any:
        with managed_connection(self._resolved_connection_factory()) as connection:
            row = self._fetch_entry_row(connection, key)
            if row is None:
                self._version_cache.pop(key, None)
                return default
            entry = self._row_to_entry(row)
            self._version_cache[key] = entry.version
            return entry.value

    def read_all(self) -> dict[str, Any]:
        entries = self.list_entries()
        return {entry.key: entry.value for entry in entries}

    def list_entries(self) -> list[StateEntry]:
        with managed_connection(self._resolved_connection_factory()) as connection:
            rows = self._fetch_entry_rows(connection)
        entries = [self._row_to_entry(row) for row in rows]
        self._version_cache.update({entry.key: entry.version for entry in entries})
        return entries

    def delete(self, key: str) -> bool:
        normalized_key = self._normalize_key(key)
        with managed_connection(self._resolved_connection_factory()) as connection:
            cursor = connection.cursor()
            parameter = placeholder(connection)
            cursor.execute(
                (
                    f"DELETE FROM {self._resolved_table_name(connection)} "
                    f"WHERE agent_id = {parameter} AND task_id = {parameter} AND key = {parameter}"
                ),
                (self.agent_id, self.task_id, normalized_key),
            )
            deleted = cursor.rowcount > 0
            connection.commit()
        if deleted:
            self._version_cache.pop(normalized_key, None)
        return deleted

    def checkpoint(self, state: dict[str, Any], ttl_hours: int | float | None = None) -> dict[str, Any]:
        if not isinstance(state, dict):
            raise ValueError("checkpoint state must be a dict")
        written_at = self._now()
        checkpoint_id = str(uuid.uuid4())
        with managed_connection(self._resolved_connection_factory()) as connection:
            for key, value in state.items():
                self._write_with_connection(connection, key, value, ttl_hours=ttl_hours, commit=False)
            rows = self._fetch_entry_rows(connection)
            connection.commit()
        entries = [self._row_to_entry(row) for row in rows]
        snapshot = {entry.key: entry.value for entry in entries}
        digest = self.compute_state_digest(snapshot)
        payload = {
            "checkpoint_id": checkpoint_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "context_id": self.context_id,
            "written_at": isoformat(written_at),
            "key_count": len(snapshot),
            "keys": sorted(snapshot),
            "state_digest": digest,
        }
        _publish_async(self._checkpoint_publisher, self._checkpoint_subject, payload)
        return payload

    def state_digest(self) -> str:
        return self.compute_state_digest(self.read_all())

    def validate_handoff(self, expected_digest: str) -> IntegrityValidationResult:
        normalized_expected = expected_digest.strip().lower()
        snapshot = self.read_all()
        actual_digest = self.compute_state_digest(snapshot)
        return IntegrityValidationResult(
            agent_id=self.agent_id,
            task_id=self.task_id,
            expected_digest=normalized_expected,
            actual_digest=actual_digest,
            matched=normalized_expected == actual_digest,
            key_count=len(snapshot),
        )

    def purge_expired(self) -> int:
        with managed_connection(self._resolved_connection_factory()) as connection:
            cursor = connection.cursor()
            parameter = placeholder(connection)
            cursor.execute(
                f"DELETE FROM {self._resolved_table_name(connection)} WHERE expires_at <= {parameter}",
                (isoformat(self._now()),),
            )
            deleted = cursor.rowcount
            connection.commit()
            return deleted

    @staticmethod
    def compute_state_digest(state: dict[str, Any]) -> str:
        payload = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _write_with_connection(
        self,
        connection: Any,
        key: str,
        value: Any,
        *,
        ttl_hours: int | float | None,
        commit: bool = False,
    ) -> None:
        normalized_key = self._normalize_key(key)
        ttl = ttl_hours if ttl_hours is not None else self.default_ttl_hours
        if ttl <= 0:
            raise ValueError("ttl_hours must be positive")
        encoded_value = self._serialize_value(value)
        written_at = self._now()
        expires_at = written_at + timedelta(hours=float(ttl))
        table_name = self._resolved_table_name(connection)
        cursor = connection.cursor()
        existing_row = self._fetch_entry_row(connection, normalized_key, include_expired=True)
        parameter = placeholder(connection)
        value_placeholder = parameter if connection_kind(connection) == "sqlite" else f"{parameter}::jsonb"
        if existing_row is None:
            if self._count_active_keys(connection) >= self.max_keys:
                raise AgentStateLimitError(
                    f"agent/task namespace {self.agent_id}/{self.task_id} already has {self.max_keys} active keys"
                )
            cursor.execute(
                (
                    f"INSERT INTO {table_name} (agent_id, task_id, key, value, context_id, written_at, expires_at, version) "
                    f"VALUES ({parameter}, {parameter}, {parameter}, {value_placeholder}, {parameter}, {parameter}, {parameter}, {parameter})"
                ),
                (
                    self.agent_id,
                    self.task_id,
                    normalized_key,
                    encoded_value,
                    self.context_id,
                    isoformat(written_at),
                    isoformat(expires_at),
                    1,
                ),
            )
            self._version_cache[normalized_key] = 1
            if commit:
                connection.commit()
            return

        cached_version = self._version_cache.get(normalized_key)
        if cached_version is None:
            next_version = int(existing_row["version"]) + 1
            cursor.execute(
                (
                    f"UPDATE {table_name} "
                    f"SET value = {value_placeholder}, context_id = {parameter}, written_at = {parameter}, "
                    f"expires_at = {parameter}, version = {parameter} "
                    f"WHERE agent_id = {parameter} AND task_id = {parameter} AND key = {parameter}"
                ),
                (
                    encoded_value,
                    self.context_id,
                    isoformat(written_at),
                    isoformat(expires_at),
                    next_version,
                    self.agent_id,
                    self.task_id,
                    normalized_key,
                ),
            )
        else:
            next_version = cached_version + 1
            cursor.execute(
                (
                    f"UPDATE {table_name} "
                    f"SET value = {value_placeholder}, context_id = {parameter}, written_at = {parameter}, "
                    f"expires_at = {parameter}, version = {parameter} "
                    f"WHERE agent_id = {parameter} AND task_id = {parameter} AND key = {parameter} "
                    f"AND version = {parameter}"
                ),
                (
                    encoded_value,
                    self.context_id,
                    isoformat(written_at),
                    isoformat(expires_at),
                    next_version,
                    self.agent_id,
                    self.task_id,
                    normalized_key,
                    cached_version,
                ),
            )
            if cursor.rowcount == 0:
                raise AgentStateConflictError(self.agent_id, self.task_id, normalized_key)

        self._version_cache[normalized_key] = next_version
        if commit:
            connection.commit()

    def _fetch_entry_row(self, connection: Any, key: str, *, include_expired: bool = False) -> dict[str, Any] | None:
        parameter = placeholder(connection)
        query = (
            f"SELECT key, value, context_id, written_at, expires_at, version "
            f"FROM {self._resolved_table_name(connection)} "
            f"WHERE agent_id = {parameter} AND task_id = {parameter} AND key = {parameter}"
        )
        params: list[Any] = [self.agent_id, self.task_id, key]
        if not include_expired:
            query += f" AND expires_at > {parameter}"
            params.append(isoformat(self._now()))
        query += " LIMIT 1"
        cursor = connection.cursor()
        cursor.execute(query, params)
        rows = rows_to_dicts(cursor)
        return rows[0] if rows else None

    def _fetch_entry_rows(self, connection: Any) -> list[dict[str, Any]]:
        parameter = placeholder(connection)
        cursor = connection.cursor()
        cursor.execute(
            (
                f"SELECT key, value, context_id, written_at, expires_at, version "
                f"FROM {self._resolved_table_name(connection)} "
                f"WHERE agent_id = {parameter} AND task_id = {parameter} AND expires_at > {parameter} "
                f"ORDER BY key"
            ),
            (self.agent_id, self.task_id, isoformat(self._now())),
        )
        return rows_to_dicts(cursor)

    def _count_active_keys(self, connection: Any) -> int:
        parameter = placeholder(connection)
        cursor = connection.cursor()
        cursor.execute(
            (
                f"SELECT COUNT(*) AS active_keys "
                f"FROM {self._resolved_table_name(connection)} "
                f"WHERE agent_id = {parameter} AND task_id = {parameter} AND expires_at > {parameter}"
            ),
            (self.agent_id, self.task_id, isoformat(self._now())),
        )
        rows = rows_to_dicts(cursor)
        return int(rows[0]["active_keys"]) if rows else 0

    def _resolved_connection_factory(self) -> ConnectionFactory:
        if self._connection_factory is not None:
            return self._connection_factory
        resolved_dsn = (self._dsn or os.environ.get("LV3_AGENT_STATE_DSN", "") or os.environ.get("WORLD_STATE_DSN", "")).strip()
        if not resolved_dsn:
            raise AgentStateError("LV3_AGENT_STATE_DSN is not set")
        return create_connection_factory(resolved_dsn)

    def _resolved_table_name(self, connection: Any) -> str:
        if self._table_name:
            return self._table_name
        return "agent_state" if connection_kind(connection) == "sqlite" else "agent.state"

    def _serialize_value(self, value: Any) -> str:
        try:
            payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        except TypeError as exc:
            raise ValueError(f"state value must be JSON-serializable: {exc}") from exc
        payload_bytes = payload.encode("utf-8")
        if len(payload_bytes) > self.max_value_bytes:
            raise AgentStateLimitError(f"state value exceeds {self.max_value_bytes} bytes")
        return payload

    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("key must be a non-empty string")
        return normalized_key

    @staticmethod
    def _row_to_entry(row: dict[str, Any]) -> StateEntry:
        return StateEntry(
            key=str(row["key"]),
            value=decode_json(row["value"]),
            context_id=str(row["context_id"]) if row.get("context_id") else None,
            written_at=parse_timestamp(row["written_at"]),
            expires_at=parse_timestamp(row["expires_at"]),
            version=int(row["version"]),
        )
