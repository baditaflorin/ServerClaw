from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any, Callable


HANDOFF_SUBJECT = "platform.agent.handoff"
HANDOFF_DSN_ENV = "LV3_HANDOFF_DSN"
HANDOFF_OPERATOR_WEBHOOK_ENV = "LV3_HANDOFF_OPERATOR_WEBHOOK_URL"
VALID_HANDOFF_TYPES = frozenset({"delegate", "escalate", "inform"})
VALID_HANDOFF_STATUSES = frozenset({"pending", "accepted", "refused", "timed_out", "escalated", "closed", "completed"})
VALID_FALLBACKS = frozenset({"operator", "close", "retry_self"})
VALID_DECISIONS = frozenset({"accept", "refuse"})
DEFAULT_SQLITE_RELATIVE_PATH = Path(".local") / "state" / "handoffs.sqlite3"


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def default_sqlite_dsn(repo_root: Path) -> str:
    return f"sqlite:///{repo_root / DEFAULT_SQLITE_RELATIVE_PATH}"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _json_loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return None
    return json.loads(value)


def _connection_kind(connection: Any) -> str:
    module_name = type(connection).__module__
    if module_name.startswith("sqlite3"):
        return "sqlite"
    return "postgres"


def _placeholder(connection: Any) -> str:
    return "?" if _connection_kind(connection) == "sqlite" else "%s"


def _row_to_mapping(cursor: Any, row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    description = getattr(cursor, "description", None) or []
    columns = [column[0] for column in description]
    return dict(zip(columns, row, strict=False))


@contextmanager
def _cursor(connection: Any) -> Any:
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


@dataclass(frozen=True)
class HandoffMessage:
    from_agent: str
    to_agent: str
    task_id: str
    subject: str
    payload: dict[str, Any]
    handoff_type: str = "delegate"
    requires_accept: bool = False
    timeout_seconds: int = 60
    fallback: str = "operator"
    context_id: str | None = None
    reply_subject: str | None = None
    handoff_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    max_retries: int = 0
    backoff_seconds: int = 5

    def __post_init__(self) -> None:
        if self.handoff_type not in VALID_HANDOFF_TYPES:
            raise ValueError(f"unsupported handoff type: {self.handoff_type}")
        if self.fallback not in VALID_FALLBACKS:
            raise ValueError(f"unsupported handoff fallback: {self.fallback}")
        if not self.from_agent.strip():
            raise ValueError("from_agent must be non-empty")
        if not self.to_agent.strip():
            raise ValueError("to_agent must be non-empty")
        if not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if not self.subject.strip():
            raise ValueError("subject must be non-empty")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dict")
        if self.timeout_seconds < 0:
            raise ValueError("timeout_seconds must be >= 0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be >= 0")
        if self.handoff_type == "inform" and self.requires_accept:
            raise ValueError("inform handoffs must not require acceptance")
        if self.handoff_type == "escalate" and not self.requires_accept:
            raise ValueError("escalate handoffs must require acceptance")

    def to_record(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass(frozen=True)
class HandoffResponse:
    handoff_id: str
    from_agent: str
    to_agent: str
    decision: str
    reason: str | None = None
    estimated_completion_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.decision not in VALID_DECISIONS:
            raise ValueError(f"unsupported handoff decision: {self.decision}")
        if not self.handoff_id.strip():
            raise ValueError("handoff_id must be non-empty")
        if not self.from_agent.strip():
            raise ValueError("from_agent must be non-empty")
        if not self.to_agent.strip():
            raise ValueError("to_agent must be non-empty")
        if self.estimated_completion_seconds is not None and self.estimated_completion_seconds < 0:
            raise ValueError("estimated_completion_seconds must be >= 0")


@dataclass(frozen=True)
class HandoffTransfer:
    handoff_id: str
    from_agent: str
    to_agent: str
    task_id: str
    context_id: str | None
    handoff_type: str
    subject: str
    payload: dict[str, Any]
    status: str
    requires_accept: bool
    timeout_seconds: int
    fallback: str
    reply_subject: str | None
    max_retries: int
    backoff_seconds: int
    sent_at: str
    responded_at: str | None = None
    completed_at: str | None = None
    response_decision: str | None = None
    response_reason: str | None = None
    estimated_completion_seconds: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "HandoffTransfer":
        return cls(
            handoff_id=str(row["handoff_id"]),
            from_agent=str(row["from_agent"]),
            to_agent=str(row["to_agent"]),
            task_id=str(row["task_id"]),
            context_id=row.get("context_id"),
            handoff_type=str(row["handoff_type"]),
            subject=str(row["subject"]),
            payload=_json_loads(row.get("payload") or "{}") or {},
            status=str(row["status"]),
            requires_accept=bool(row["requires_accept"]),
            timeout_seconds=int(row["timeout_seconds"]),
            fallback=str(row["fallback"]),
            reply_subject=row.get("reply_subject"),
            max_retries=int(row.get("max_retries") or 0),
            backoff_seconds=int(row.get("backoff_seconds") or 0),
            sent_at=str(row["sent_at"]),
            responded_at=row.get("responded_at"),
            completed_at=row.get("completed_at"),
            response_decision=row.get("response_decision"),
            response_reason=row.get("response_reason"),
            estimated_completion_seconds=(
                int(row["estimated_completion_seconds"])
                if row.get("estimated_completion_seconds") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HandoffStore:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        connection: Any = None,
        connect: Callable[[str], Any] | None = None,
        table_name: str | None = None,
    ) -> None:
        self._dsn = dsn
        self._connection = connection
        self._connect = connect
        self._table_name = table_name
        self._write_lock = threading.Lock()

    def _resolved_dsn(self) -> str:
        resolved = (self._dsn or os.environ.get(HANDOFF_DSN_ENV, "")).strip()
        if not resolved:
            raise RuntimeError(f"{HANDOFF_DSN_ENV} is not configured")
        return resolved

    def _connect_sqlite(self, sqlite_path: str) -> sqlite3.Connection:
        path = Path(sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _resolve_connection(self) -> tuple[Any, bool]:
        if self._connection is not None:
            return self._connection, False
        dsn = self._resolved_dsn()
        if dsn.startswith("sqlite:///"):
            return self._connect_sqlite(dsn.removeprefix("sqlite:///")), True
        connector = self._connect
        if connector is None:
            try:
                import psycopg2  # type: ignore
            except ModuleNotFoundError as exc:  # pragma: no cover - runtime-only dependency
                raise RuntimeError("psycopg2 is required for non-sqlite handoff DSNs") from exc
            connector = psycopg2.connect
        return connector(dsn), True

    def _table_name_for(self, connection: Any) -> str:
        if self._table_name:
            return self._table_name
        if _connection_kind(connection) == "sqlite":
            return "handoff_transfers"
        return "handoff.transfers"

    def ensure_schema(self) -> None:
        connection, owned_connection = self._resolve_connection()
        try:
            table_name = self._table_name_for(connection)
            with _cursor(connection) as cursor:
                if _connection_kind(connection) == "sqlite":
                    cursor.executescript(
                        f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            handoff_id TEXT PRIMARY KEY,
                            from_agent TEXT NOT NULL,
                            to_agent TEXT NOT NULL,
                            task_id TEXT NOT NULL,
                            context_id TEXT,
                            handoff_type TEXT NOT NULL,
                            subject TEXT NOT NULL,
                            payload TEXT NOT NULL,
                            status TEXT NOT NULL,
                            requires_accept INTEGER NOT NULL,
                            timeout_seconds INTEGER NOT NULL,
                            fallback TEXT NOT NULL,
                            reply_subject TEXT,
                            max_retries INTEGER NOT NULL DEFAULT 0,
                            backoff_seconds INTEGER NOT NULL DEFAULT 5,
                            sent_at TEXT NOT NULL,
                            responded_at TEXT,
                            completed_at TEXT,
                            response_decision TEXT,
                            response_reason TEXT,
                            estimated_completion_seconds INTEGER
                        );
                        CREATE INDEX IF NOT EXISTS {table_name}_to_idx ON {table_name} (to_agent, status);
                        CREATE INDEX IF NOT EXISTS {table_name}_task_idx ON {table_name} (task_id);
                        """
                    )
                else:
                    cursor.execute("CREATE SCHEMA IF NOT EXISTS handoff")
                    cursor.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            handoff_id UUID PRIMARY KEY,
                            from_agent TEXT NOT NULL,
                            to_agent TEXT NOT NULL,
                            task_id TEXT NOT NULL,
                            context_id UUID,
                            handoff_type TEXT NOT NULL,
                            subject TEXT NOT NULL,
                            payload JSONB NOT NULL,
                            status TEXT NOT NULL,
                            requires_accept BOOLEAN NOT NULL,
                            timeout_seconds INTEGER NOT NULL,
                            fallback TEXT NOT NULL,
                            reply_subject TEXT,
                            max_retries INTEGER NOT NULL DEFAULT 0,
                            backoff_seconds INTEGER NOT NULL DEFAULT 5,
                            sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                            responded_at TIMESTAMPTZ,
                            completed_at TIMESTAMPTZ,
                            response_decision TEXT,
                            response_reason TEXT,
                            estimated_completion_seconds INTEGER
                        )
                        """
                    )
                    cursor.execute(
                        f"CREATE INDEX IF NOT EXISTS handoff_transfers_to_idx ON {table_name} (to_agent, status)"
                    )
                    cursor.execute(
                        f"CREATE INDEX IF NOT EXISTS handoff_transfers_task_idx ON {table_name} (task_id)"
                    )
            connection.commit()
        finally:
            if owned_connection:
                connection.close()

    def _fetch_one(self, cursor: Any) -> HandoffTransfer | None:
        row = cursor.fetchone()
        if row is None:
            return None
        return HandoffTransfer.from_row(_row_to_mapping(cursor, row))

    def get_transfer(self, handoff_id: str) -> HandoffTransfer | None:
        connection, owned_connection = self._resolve_connection()
        try:
            table_name = self._table_name_for(connection)
            placeholder = _placeholder(connection)
            with _cursor(connection) as cursor:
                cursor.execute(f"SELECT * FROM {table_name} WHERE handoff_id = {placeholder}", (handoff_id,))
                return self._fetch_one(cursor)
        finally:
            if owned_connection:
                connection.close()

    def list_transfers(
        self,
        *,
        task_id: str | None = None,
        to_agent: str | None = None,
        from_agent: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[HandoffTransfer]:
        connection, owned_connection = self._resolve_connection()
        try:
            table_name = self._table_name_for(connection)
            placeholder = _placeholder(connection)
            clauses: list[str] = []
            params: list[Any] = []
            if task_id:
                clauses.append(f"task_id = {placeholder}")
                params.append(task_id)
            if to_agent:
                clauses.append(f"to_agent = {placeholder}")
                params.append(to_agent)
            if from_agent:
                clauses.append(f"from_agent = {placeholder}")
                params.append(from_agent)
            if status:
                clauses.append(f"status = {placeholder}")
                params.append(status)
            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            with _cursor(connection) as cursor:
                cursor.execute(
                    f"SELECT * FROM {table_name} {where_sql} ORDER BY sent_at DESC LIMIT {placeholder}",
                    tuple(params),
                )
                return [HandoffTransfer.from_row(_row_to_mapping(cursor, row)) for row in cursor.fetchall()]
        finally:
            if owned_connection:
                connection.close()

    def record_send(self, message: HandoffMessage) -> HandoffTransfer:
        with self._write_lock:
            connection, owned_connection = self._resolve_connection()
            try:
                table_name = self._table_name_for(connection)
                existing = self.get_transfer(message.handoff_id)
                if existing is not None:
                    return existing
                now_text = isoformat(utc_now())
                with _cursor(connection) as cursor:
                    if _connection_kind(connection) == "sqlite":
                        cursor.execute(
                            f"""
                            INSERT INTO {table_name} (
                                handoff_id, from_agent, to_agent, task_id, context_id, handoff_type, subject,
                                payload, status, requires_accept, timeout_seconds, fallback, reply_subject,
                                max_retries, backoff_seconds, sent_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                message.handoff_id,
                                message.from_agent,
                                message.to_agent,
                                message.task_id,
                                message.context_id,
                                message.handoff_type,
                                message.subject,
                                _json_dumps(message.payload),
                                "pending",
                                int(message.requires_accept),
                                message.timeout_seconds,
                                message.fallback,
                                message.reply_subject,
                                message.max_retries,
                                message.backoff_seconds,
                                now_text,
                            ),
                        )
                    else:
                        cursor.execute(
                            f"""
                            INSERT INTO {table_name} (
                                handoff_id, from_agent, to_agent, task_id, context_id, handoff_type, subject,
                                payload, status, requires_accept, timeout_seconds, fallback, reply_subject,
                                max_retries, backoff_seconds, sent_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                message.handoff_id,
                                message.from_agent,
                                message.to_agent,
                                message.task_id,
                                message.context_id,
                                message.handoff_type,
                                message.subject,
                                _json_dumps(message.payload),
                                "pending",
                                message.requires_accept,
                                message.timeout_seconds,
                                message.fallback,
                                message.reply_subject,
                                message.max_retries,
                                message.backoff_seconds,
                                now_text,
                            ),
                        )
                connection.commit()
                created = self.get_transfer(message.handoff_id)
                if created is None:
                    raise RuntimeError("handoff transfer insert returned no row")
                return created
            finally:
                if owned_connection:
                    connection.close()

    def record_response(self, response: HandoffResponse) -> HandoffTransfer:
        with self._write_lock:
            connection, owned_connection = self._resolve_connection()
            try:
                table_name = self._table_name_for(connection)
                current = self.get_transfer(response.handoff_id)
                if current is None:
                    raise KeyError(f"unknown handoff {response.handoff_id}")
                status = "accepted" if response.decision == "accept" else "refused"
                responded_at = isoformat(utc_now())
                with _cursor(connection) as cursor:
                    if _connection_kind(connection) == "sqlite":
                        cursor.execute(
                            f"""
                            UPDATE {table_name}
                            SET status = ?, responded_at = ?, response_decision = ?, response_reason = ?,
                                estimated_completion_seconds = ?
                            WHERE handoff_id = ?
                            """,
                            (
                                status,
                                responded_at,
                                response.decision,
                                response.reason,
                                response.estimated_completion_seconds,
                                response.handoff_id,
                            ),
                        )
                    else:
                        cursor.execute(
                            f"""
                            UPDATE {table_name}
                            SET status = %s, responded_at = %s, response_decision = %s, response_reason = %s,
                                estimated_completion_seconds = %s
                            WHERE handoff_id = %s
                            """,
                            (
                                status,
                                responded_at,
                                response.decision,
                                response.reason,
                                response.estimated_completion_seconds,
                                response.handoff_id,
                            ),
                        )
                connection.commit()
                updated = self.get_transfer(response.handoff_id)
                if updated is None:
                    raise RuntimeError("handoff transfer update returned no row")
                return updated
            finally:
                if owned_connection:
                    connection.close()

    def set_status(
        self,
        handoff_id: str,
        *,
        status: str,
        response_reason: str | None = None,
        completed: bool = False,
    ) -> HandoffTransfer:
        if status not in VALID_HANDOFF_STATUSES:
            raise ValueError(f"unsupported handoff status: {status}")
        with self._write_lock:
            connection, owned_connection = self._resolve_connection()
            try:
                table_name = self._table_name_for(connection)
                timestamp = isoformat(utc_now())
                completed_at = timestamp if completed else None
                with _cursor(connection) as cursor:
                    if _connection_kind(connection) == "sqlite":
                        cursor.execute(
                            f"""
                            UPDATE {table_name}
                            SET status = ?, response_reason = COALESCE(?, response_reason),
                                responded_at = CASE WHEN ? = 'timed_out' THEN ? ELSE responded_at END,
                                completed_at = COALESCE(?, completed_at)
                            WHERE handoff_id = ?
                            """,
                            (status, response_reason, status, timestamp, completed_at, handoff_id),
                        )
                    else:
                        cursor.execute(
                            f"""
                            UPDATE {table_name}
                            SET status = %s, response_reason = COALESCE(%s, response_reason),
                                responded_at = CASE WHEN %s = 'timed_out' THEN %s ELSE responded_at END,
                                completed_at = COALESCE(%s, completed_at)
                            WHERE handoff_id = %s
                            """,
                            (status, response_reason, status, timestamp, completed_at, handoff_id),
                        )
                connection.commit()
                updated = self.get_transfer(handoff_id)
                if updated is None:
                    raise KeyError(f"unknown handoff {handoff_id}")
                return updated
            finally:
                if owned_connection:
                    connection.close()


class InMemoryHandoffBus:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[HandoffMessage], HandoffResponse | None]] = {}
        self._lock = threading.Lock()

    def register(self, agent_id: str, handler: Callable[[HandoffMessage], HandoffResponse | None]) -> None:
        with self._lock:
            self._handlers[agent_id] = handler

    def deliver(self, message: HandoffMessage) -> HandoffResponse | None:
        with self._lock:
            handler = self._handlers.get(message.to_agent)
        if handler is None:
            return None
        return handler(message)


class HandoffClient:
    def __init__(
        self,
        *,
        store: HandoffStore,
        bus: Any | None = None,
        ledger_writer: Any | None = None,
        operator_notifier: Callable[[HandoffTransfer, str | None], None] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = store
        self._bus = bus
        self._ledger_writer = ledger_writer
        self._operator_notifier = operator_notifier
        self._sleep_fn = sleep_fn

    @property
    def store(self) -> HandoffStore:
        return self._store

    def send(self, message: HandoffMessage) -> HandoffTransfer:
        transfer = self._store.record_send(message)
        self._write_ledger(
            "handoff.transfer_recorded",
            actor=message.from_agent,
            transfer=transfer,
            metadata={"subject": HANDOFF_SUBJECT, "task_id": message.task_id},
        )
        if message.to_agent == "operator":
            self._notify_operator(transfer, None)
            return transfer
        if self._bus is None:
            return transfer

        final_response: HandoffResponse | None = None
        for attempt in range(message.max_retries + 1):
            response = self._bus.deliver(message)
            if response is None:
                if not message.requires_accept:
                    return transfer
                if attempt < message.max_retries:
                    self._sleep_fn(message.backoff_seconds)
                    continue
                return self._apply_timeout(transfer, reason="acceptance_timeout")
            if response.decision == "refuse" and response.reason == "busy" and attempt < message.max_retries:
                self._sleep_fn(message.backoff_seconds)
                continue
            final_response = response
            break

        if final_response is None:
            return transfer

        transfer = self._store.record_response(final_response)
        self._write_ledger(
            "handoff.accepted" if final_response.decision == "accept" else "handoff.refused",
            actor=final_response.from_agent,
            transfer=transfer,
            metadata={"decision_reason": final_response.reason},
        )
        if final_response.decision == "refuse":
            return self._apply_fallback(transfer, final_response.reason)
        return transfer

    def accept(
        self,
        handoff_id: str,
        *,
        actor: str,
        estimated_completion_seconds: int | None = None,
    ) -> HandoffTransfer:
        current = self._require_transfer(handoff_id)
        response = HandoffResponse(
            handoff_id=handoff_id,
            from_agent=actor,
            to_agent=current.from_agent,
            decision="accept",
            estimated_completion_seconds=estimated_completion_seconds,
        )
        updated = self._store.record_response(response)
        self._write_ledger("handoff.accepted", actor=actor, transfer=updated, metadata={})
        return updated

    def refuse(self, handoff_id: str, *, actor: str, reason: str) -> HandoffTransfer:
        current = self._require_transfer(handoff_id)
        response = HandoffResponse(
            handoff_id=handoff_id,
            from_agent=actor,
            to_agent=current.from_agent,
            decision="refuse",
            reason=reason,
        )
        updated = self._store.record_response(response)
        self._write_ledger("handoff.refused", actor=actor, transfer=updated, metadata={"decision_reason": reason})
        return self._apply_fallback(updated, reason)

    def complete(self, handoff_id: str, *, actor: str) -> HandoffTransfer:
        updated = self._store.set_status(handoff_id, status="completed", completed=True)
        self._write_ledger("handoff.completed", actor=actor, transfer=updated, metadata={})
        return updated

    def _require_transfer(self, handoff_id: str) -> HandoffTransfer:
        transfer = self._store.get_transfer(handoff_id)
        if transfer is None:
            raise KeyError(f"unknown handoff {handoff_id}")
        return transfer

    def _apply_timeout(self, transfer: HandoffTransfer, *, reason: str) -> HandoffTransfer:
        timed_out = self._store.set_status(transfer.handoff_id, status="timed_out", response_reason=reason)
        self._write_ledger("handoff.timed_out", actor=transfer.from_agent, transfer=timed_out, metadata={"reason": reason})
        return self._apply_fallback(timed_out, reason)

    def _apply_fallback(self, transfer: HandoffTransfer, reason: str | None) -> HandoffTransfer:
        if transfer.fallback == "operator":
            escalated = self._store.set_status(transfer.handoff_id, status="escalated", response_reason=reason)
            self._notify_operator(escalated, reason)
            self._write_ledger(
                "handoff.escalated_to_operator",
                actor=transfer.from_agent,
                transfer=escalated,
                metadata={"reason": reason},
            )
            return escalated
        closed = self._store.set_status(transfer.handoff_id, status="closed", response_reason=reason)
        self._write_ledger(
            "handoff.closed_unaccepted",
            actor=transfer.from_agent,
            transfer=closed,
            metadata={"reason": reason, "fallback": transfer.fallback},
        )
        return closed

    def _notify_operator(self, transfer: HandoffTransfer, reason: str | None) -> None:
        notifier = self._operator_notifier
        if notifier is None:
            webhook_url = os.environ.get(HANDOFF_OPERATOR_WEBHOOK_ENV, "").strip()
            if not webhook_url:
                return

            def post_webhook(record: HandoffTransfer, why: str | None) -> None:
                payload = {
                    "text": f"Handoff {record.handoff_id} for {record.subject}",
                    "handoff": record.to_dict(),
                    "reason": why,
                }
                request = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=10):
                        return
                except urllib.error.URLError:
                    return

            notifier = post_webhook
        try:
            notifier(transfer, reason)
        except Exception:
            return

    def _write_ledger(self, event_type: str, *, actor: str, transfer: HandoffTransfer, metadata: dict[str, Any]) -> None:
        if self._ledger_writer is None:
            return
        try:
            self._ledger_writer.write(
                event_type=event_type,
                actor=actor,
                target_kind="agent_handoff",
                target_id=transfer.handoff_id,
                after_state=transfer.to_dict(),
                metadata=metadata,
            )
        except Exception:
            return
