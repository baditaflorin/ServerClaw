from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator


ConnectionFactory = Callable[[], Any]


def create_connection_factory(dsn: str) -> ConnectionFactory:
    resolved = dsn.strip()
    if not resolved:
        raise RuntimeError("a config-merge DSN is required")

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
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "psycopg is required for postgres config-merge DSNs; install it or use sqlite:/// for tests."
            ) from exc

        return psycopg.connect(resolved)

    return connect_postgres


def connection_kind(connection: Any) -> str:
    module_name = type(connection).__module__
    if module_name.startswith("sqlite3"):
        return "sqlite"
    return "postgres"


def placeholder(connection: Any) -> str:
    return "?" if connection_kind(connection) == "sqlite" else "%s"


@contextmanager
def managed_connection(connection_factory: ConnectionFactory | None = None, dsn: str | None = None) -> Iterator[Any]:
    if connection_factory is None:
        if dsn is None or not dsn.strip():
            raise RuntimeError("a config-merge DSN is required when no connection factory is supplied")
        connection_factory = create_connection_factory(dsn)
    connection = connection_factory()
    try:
        yield connection
    finally:
        connection.close()


def rows_to_dicts(cursor: Any) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row, strict=False)) for row in rows]
