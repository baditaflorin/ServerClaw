from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator


ConnectionFactory = Callable[[], Any]


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_dsn() -> str:
    return os.environ.get("WORLD_STATE_DSN", "").strip()


def create_connection_factory(dsn: str | None = None) -> ConnectionFactory:
    resolved = (dsn or default_dsn()).strip()
    if not resolved:
        raise RuntimeError("WORLD_STATE_DSN is not set")

    if resolved.startswith("sqlite:///"):
        sqlite_path = resolved.removeprefix("sqlite:///")

        def connect_sqlite() -> sqlite3.Connection:
            connection = sqlite3.connect(Path(sqlite_path))
            connection.row_factory = sqlite3.Row
            return connection

        return connect_sqlite

    def connect_postgres() -> Any:
        try:
            import psycopg
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime-only dependency
            raise RuntimeError(
                "psycopg is required for postgres WORLD_STATE_DSN values; install it or use sqlite:/// for tests."
            ) from exc

        return psycopg.connect(resolved)

    return connect_postgres


def connection_kind(connection: Any) -> str:
    module_name = type(connection).__module__
    if module_name.startswith("sqlite3"):
        return "sqlite"
    return "postgres"


@contextmanager
def managed_connection(connection_factory: ConnectionFactory | None = None, dsn: str | None = None) -> Iterator[Any]:
    factory = connection_factory or create_connection_factory(dsn)
    connection = factory()
    try:
        yield connection
    finally:
        connection.close()


def placeholder(connection: Any) -> str:
    return "?" if connection_kind(connection) == "sqlite" else "%s"


def decode_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def rows_to_dicts(cursor: Any) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row, strict=False)) for row in rows]
