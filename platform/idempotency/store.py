from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from platform.world_state._db import (
    ConnectionFactory,
    connection_kind,
    create_connection_factory,
    decode_json,
    isoformat,
    managed_connection,
    parse_timestamp,
    placeholder,
    utc_now,
)


DEFAULT_STATE_SUBPATH = Path("lv3-idempotency") / "records.json"
DEFAULT_TTL_HOURS = 2


def _git_common_dir(repo_root: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def _default_state_path(repo_root: Path) -> Path:
    override = os.environ.get("LV3_IDEMPOTENCY_STATE_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    common_dir = _git_common_dir(repo_root)
    if common_dir is not None:
        return common_dir / DEFAULT_STATE_SUBPATH
    return repo_root / ".local" / "state" / "idempotency" / "records.json"


@dataclass(frozen=True)
class IdempotencyRecord:
    idempotency_key: str
    workflow_id: str
    actor_id: str
    actor_intent_id: str | None
    target_service_id: str
    status: str
    submitted_at: str
    expires_at: str
    completed_at: str | None = None
    windmill_job_id: str | None = None
    result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "workflow_id": self.workflow_id,
            "actor_id": self.actor_id,
            "actor_intent_id": self.actor_intent_id,
            "target_service_id": self.target_service_id,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "expires_at": self.expires_at,
            "completed_at": self.completed_at,
            "windmill_job_id": self.windmill_job_id,
            "result": self.result,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IdempotencyRecord":
        return cls(
            idempotency_key=str(payload["idempotency_key"]),
            workflow_id=str(payload["workflow_id"]),
            actor_id=str(payload["actor_id"]),
            actor_intent_id=str(payload["actor_intent_id"]) if payload.get("actor_intent_id") else None,
            target_service_id=str(payload.get("target_service_id") or ""),
            status=str(payload["status"]),
            submitted_at=str(payload["submitted_at"]),
            expires_at=str(payload["expires_at"]),
            completed_at=str(payload["completed_at"]) if payload.get("completed_at") else None,
            windmill_job_id=str(payload["windmill_job_id"]) if payload.get("windmill_job_id") else None,
            result=payload.get("result"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class IdempotencyClaim:
    action: str
    record: IdempotencyRecord


class IdempotencyStore:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        dsn: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        state_path: Path | None = None,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        now_fn: Any | None = None,
    ) -> None:
        self._repo_root = repo_root or Path(__file__).resolve().parents[2]
        self._dsn = dsn
        self._connection_factory = connection_factory
        self._state_path = state_path or _default_state_path(self._repo_root)
        self._lock_path = self._state_path.with_suffix(".lock")
        self._ttl_hours = ttl_hours
        self._now = now_fn or utc_now

    def claim(
        self,
        *,
        idempotency_key: str,
        workflow_id: str,
        actor_id: str,
        actor_intent_id: str | None,
        target_service_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> IdempotencyClaim:
        now = self._now()
        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            workflow_id=workflow_id,
            actor_id=actor_id,
            actor_intent_id=actor_intent_id,
            target_service_id=target_service_id,
            status="in_flight",
            submitted_at=isoformat(now),
            expires_at=isoformat(now + timedelta(hours=self._ttl_hours)),
            metadata=dict(metadata or {}),
        )
        if self._resolved_connection_factory() is not None:
            return self._claim_sql(record, now)
        return self._claim_file(record)

    def attach_job_id(self, idempotency_key: str, job_id: str) -> None:
        if self._resolved_connection_factory() is not None:
            self._update_sql(idempotency_key, {"windmill_job_id": job_id})
            return
        self._update_file(idempotency_key, {"windmill_job_id": job_id})

    def complete(self, idempotency_key: str, *, status: str, result: Any = None, job_id: str | None = None) -> None:
        updates = {
            "status": status,
            "result": result,
            "completed_at": isoformat(self._now()),
        }
        if job_id is not None:
            updates["windmill_job_id"] = job_id
        if self._resolved_connection_factory() is not None:
            self._update_sql(idempotency_key, updates)
            return
        self._update_file(idempotency_key, updates)

    def delete(self, idempotency_key: str) -> bool:
        if self._resolved_connection_factory() is not None:
            return self._delete_sql(idempotency_key)
        return self._delete_file(idempotency_key)

    def record_for_intent(self, actor_intent_id: str) -> IdempotencyRecord | None:
        if self._resolved_connection_factory() is not None:
            return self._record_for_intent_sql(actor_intent_id)
        return self._record_for_intent_file(actor_intent_id)

    def record_for_key(self, idempotency_key: str) -> IdempotencyRecord | None:
        if self._resolved_connection_factory() is not None:
            return self._record_for_key_sql(idempotency_key)
        return self._record_for_key_file(idempotency_key)

    def _resolved_connection_factory(self) -> ConnectionFactory | None:
        if self._connection_factory is not None:
            return self._connection_factory
        resolved_dsn = (
            self._dsn
            or os.environ.get("LV3_IDEMPOTENCY_DSN", "").strip()
            or os.environ.get("LV3_LEDGER_DSN", "").strip()
        )
        if not resolved_dsn:
            return None
        self._dsn = resolved_dsn
        self._connection_factory = create_connection_factory(resolved_dsn)
        return self._connection_factory

    @staticmethod
    def _table_name(connection: Any) -> str:
        return "platform_idempotency_records" if connection_kind(connection) == "sqlite" else "platform.idempotency_records"

    @staticmethod
    def _json_placeholder(connection: Any) -> str:
        base = placeholder(connection)
        return base if connection_kind(connection) == "sqlite" else f"{base}::jsonb"

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> IdempotencyRecord:
        payload = dict(row)
        payload["result"] = decode_json(payload.get("result"))
        payload["metadata"] = decode_json(payload.get("metadata")) if payload.get("metadata") is not None else {}
        return IdempotencyRecord.from_dict(payload)

    @contextmanager
    def _locked_file_state(self) -> Iterator[dict[str, Any]]:
        import fcntl

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            state = self._read_state_file()
            self._purge_state(state, self._now())
            yield state
            self._state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_state_file(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {"records": {}}
        payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"records": {}}
        payload.setdefault("records", {})
        return payload

    @staticmethod
    def _purge_state(state: dict[str, Any], now: datetime) -> None:
        records = state.setdefault("records", {})
        for key, payload in list(records.items()):
            if not isinstance(payload, dict):
                records.pop(key, None)
                continue
            expires_at = payload.get("expires_at")
            if not expires_at:
                continue
            if parse_timestamp(str(expires_at)) <= now:
                records.pop(key, None)

    def _claim_file(self, record: IdempotencyRecord) -> IdempotencyClaim:
        with self._locked_file_state() as state:
            records = state.setdefault("records", {})
            existing_payload = records.get(record.idempotency_key)
            if isinstance(existing_payload, dict):
                existing = IdempotencyRecord.from_dict(existing_payload)
                if existing.status == "completed":
                    return IdempotencyClaim(action="completed", record=existing)
                if existing.status == "in_flight":
                    return IdempotencyClaim(action="in_flight", record=existing)
                records.pop(record.idempotency_key, None)
            records[record.idempotency_key] = record.as_dict()
            return IdempotencyClaim(action="created", record=record)

    def _update_file(self, idempotency_key: str, updates: dict[str, Any]) -> None:
        with self._locked_file_state() as state:
            records = state.setdefault("records", {})
            payload = records.get(idempotency_key)
            if not isinstance(payload, dict):
                return
            payload.update(updates)

    def _delete_file(self, idempotency_key: str) -> bool:
        with self._locked_file_state() as state:
            records = state.setdefault("records", {})
            return records.pop(idempotency_key, None) is not None

    def _record_for_intent_file(self, actor_intent_id: str) -> IdempotencyRecord | None:
        with self._locked_file_state() as state:
            matches: list[IdempotencyRecord] = []
            for payload in state.get("records", {}).values():
                if not isinstance(payload, dict):
                    continue
                if payload.get("actor_intent_id") != actor_intent_id:
                    continue
                matches.append(IdempotencyRecord.from_dict(payload))
            if not matches:
                return None
            return sorted(matches, key=lambda item: item.submitted_at)[-1]

    def _record_for_key_file(self, idempotency_key: str) -> IdempotencyRecord | None:
        with self._locked_file_state() as state:
            payload = state.get("records", {}).get(idempotency_key)
            if not isinstance(payload, dict):
                return None
            return IdempotencyRecord.from_dict(payload)

    def _claim_sql(self, record: IdempotencyRecord, now: datetime) -> IdempotencyClaim:
        factory = self._resolved_connection_factory()
        assert factory is not None
        with managed_connection(factory) as connection:
            table = self._table_name(connection)
            value_placeholder = self._json_placeholder(connection)
            param = placeholder(connection)
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM {table} WHERE expires_at <= {param}", (isoformat(now),))
            for _ in range(2):
                existing = self._record_for_key_sql(record.idempotency_key, connection=connection)
                if existing is not None:
                    if existing.status == "completed":
                        connection.commit()
                        return IdempotencyClaim(action="completed", record=existing)
                    if existing.status == "in_flight":
                        connection.commit()
                        return IdempotencyClaim(action="in_flight", record=existing)
                    cursor.execute(f"DELETE FROM {table} WHERE idempotency_key = {param}", (record.idempotency_key,))
                cursor.execute(
                    (
                        f"INSERT INTO {table} "
                        "(idempotency_key, workflow_id, actor_id, actor_intent_id, target_service_id, status, submitted_at, expires_at, metadata) "
                        f"VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param}, {value_placeholder}) "
                        "ON CONFLICT(idempotency_key) DO NOTHING"
                    ),
                    (
                        record.idempotency_key,
                        record.workflow_id,
                        record.actor_id,
                        record.actor_intent_id,
                        record.target_service_id,
                        record.status,
                        record.submitted_at,
                        record.expires_at,
                        json.dumps(record.metadata, sort_keys=True),
                    ),
                )
                if cursor.rowcount == 1:
                    connection.commit()
                    return IdempotencyClaim(action="created", record=record)
            resolved = self._record_for_key_sql(record.idempotency_key, connection=connection)
            connection.commit()
            if resolved is None:
                return IdempotencyClaim(action="created", record=record)
            action = "completed" if resolved.status == "completed" else "in_flight"
            return IdempotencyClaim(action=action, record=resolved)

    def _update_sql(self, idempotency_key: str, updates: dict[str, Any]) -> None:
        factory = self._resolved_connection_factory()
        assert factory is not None
        with managed_connection(factory) as connection:
            table = self._table_name(connection)
            param = placeholder(connection)
            value_placeholder = self._json_placeholder(connection)
            assignments: list[str] = []
            params: list[Any] = []
            for key, value in updates.items():
                if key in {"result", "metadata"}:
                    assignments.append(f"{key} = {value_placeholder}")
                    params.append(json.dumps(value, sort_keys=True) if value is not None else None)
                else:
                    assignments.append(f"{key} = {param}")
                    params.append(value)
            params.append(idempotency_key)
            connection.cursor().execute(
                f"UPDATE {table} SET {', '.join(assignments)} WHERE idempotency_key = {param}",
                tuple(params),
            )
            connection.commit()

    def _delete_sql(self, idempotency_key: str) -> bool:
        factory = self._resolved_connection_factory()
        assert factory is not None
        with managed_connection(factory) as connection:
            table = self._table_name(connection)
            param = placeholder(connection)
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM {table} WHERE idempotency_key = {param}", (idempotency_key,))
            connection.commit()
            return cursor.rowcount > 0

    def _record_for_intent_sql(self, actor_intent_id: str, *, connection: Any | None = None) -> IdempotencyRecord | None:
        if connection is not None:
            return self._query_record(
                connection,
                "actor_intent_id",
                actor_intent_id,
                order_by="submitted_at DESC",
            )
        factory = self._resolved_connection_factory()
        assert factory is not None
        with managed_connection(factory) as managed:
            return self._record_for_intent_sql(actor_intent_id, connection=managed)

    def _record_for_key_sql(self, idempotency_key: str, *, connection: Any | None = None) -> IdempotencyRecord | None:
        if connection is not None:
            return self._query_record(connection, "idempotency_key", idempotency_key)
        factory = self._resolved_connection_factory()
        assert factory is not None
        with managed_connection(factory) as managed:
            return self._record_for_key_sql(idempotency_key, connection=managed)

    def _query_record(self, connection: Any, column: str, value: str, *, order_by: str = "submitted_at ASC") -> IdempotencyRecord | None:
        table = self._table_name(connection)
        param = placeholder(connection)
        cursor = connection.cursor()
        cursor.execute(
            (
                "SELECT "
                "idempotency_key, workflow_id, actor_id, actor_intent_id, target_service_id, status, "
                "submitted_at, expires_at, completed_at, windmill_job_id, result, metadata "
                f"FROM {table} WHERE {column} = {param} ORDER BY {order_by} LIMIT 1"
            ),
            (value,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        if hasattr(row, "keys"):
            payload = dict(row)
        else:
            payload = dict(zip([column[0] for column in cursor.description], row, strict=False))
        return self._row_to_record(payload)
