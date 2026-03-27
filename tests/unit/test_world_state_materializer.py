from __future__ import annotations

from typing import Any

from platform.world_state.materializer import materialize_surface


class FakeCursor:
    def __init__(self, connection: "FakePostgresConnection") -> None:
        self.connection = connection
        self._results: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        normalized = " ".join(sql.split())
        self.connection.queries.append((normalized, params))
        if normalized.startswith("SELECT ispopulated FROM pg_matviews"):
            self._results = [(self.connection.ispopulated,)]
            return
        self._results = []

    def fetchone(self) -> tuple[Any, ...] | None:
        if not self._results:
            return None
        return self._results[0]


class FakePostgresConnection:
    def __init__(self, *, ispopulated: bool) -> None:
        self.ispopulated = ispopulated
        self.queries: list[tuple[str, list[Any] | None]] = []
        self.commit_count = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_count += 1

    def close(self) -> None:
        return None


def connection_factory(*, ispopulated: bool):
    def factory() -> FakePostgresConnection:
        return FakePostgresConnection(ispopulated=ispopulated)

    return factory


def test_materialize_surface_populates_uninitialized_postgres_view() -> None:
    connection = FakePostgresConnection(ispopulated=False)

    materialize_surface(
        "proxmox_vms",
        [{"vmid": 110, "name": "nginx-lv3", "status": "running"}],
        connection_factory=lambda: connection,
    )

    statements = [sql for sql, _ in connection.queries]
    assert "REFRESH MATERIALIZED VIEW world_state.current_view" in statements
    assert "REFRESH MATERIALIZED VIEW CONCURRENTLY world_state.current_view" not in statements
    assert connection.commit_count == 2


def test_materialize_surface_uses_concurrent_refresh_once_view_is_populated() -> None:
    connection = FakePostgresConnection(ispopulated=True)

    materialize_surface(
        "proxmox_vms",
        [{"vmid": 110, "name": "nginx-lv3", "status": "running"}],
        connection_factory=lambda: connection,
    )

    statements = [sql for sql, _ in connection.queries]
    assert "REFRESH MATERIALIZED VIEW CONCURRENTLY world_state.current_view" in statements
