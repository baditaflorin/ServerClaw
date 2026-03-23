from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ._db import (
    ConnectionFactory,
    create_connection_factory,
    decode_json,
    managed_connection,
    parse_timestamp,
    placeholder,
    rows_to_dicts,
)


class WorldStateError(RuntimeError):
    pass


class SurfaceNotFoundError(WorldStateError):
    def __init__(self, surface: str):
        super().__init__(f"World-state surface '{surface}' was not found")
        self.surface = surface


class StaleDataError(WorldStateError):
    def __init__(self, surface: str, collected_at: datetime, *, stale: bool, is_expired: bool):
        super().__init__(
            f"World-state surface '{surface}' is stale "
            f"(collected_at={collected_at.isoformat()}, stale={stale}, is_expired={is_expired})"
        )
        self.surface = surface
        self.collected_at = collected_at
        self.stale = stale
        self.is_expired = is_expired


@dataclass(frozen=True)
class SurfaceSnapshot:
    surface: str
    data: Any
    collected_at: datetime
    stale: bool
    is_expired: bool


class WorldStateClient:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        current_view_name: str = "world_state.current_view",
        snapshots_table_name: str = "world_state.snapshots",
    ):
        self._connection_factory = connection_factory or create_connection_factory(dsn)
        self.current_view_name = current_view_name
        self.snapshots_table_name = snapshots_table_name

    def get(self, surface: str, *, allow_stale: bool = False) -> Any:
        snapshot = self.get_snapshot(surface, allow_stale=allow_stale)
        return snapshot.data

    def get_snapshot(self, surface: str, *, allow_stale: bool = False) -> SurfaceSnapshot:
        row = self._fetch_one(
            lambda parameter: (
                f"SELECT surface, data, collected_at, stale, is_expired "
                f"FROM {self.current_view_name} WHERE surface = {parameter}"
            ),
            [surface],
        )
        if row is None:
            raise SurfaceNotFoundError(surface)
        snapshot = self._row_to_snapshot(row)
        self._raise_if_stale(snapshot, allow_stale=allow_stale)
        return snapshot

    def get_at(self, surface: str, *, at: str | datetime) -> Any:
        row = self._fetch_one(
            lambda parameter: (
                f"SELECT surface, data, collected_at, stale "
                f"FROM {self.snapshots_table_name} "
                f"WHERE surface = {parameter} AND collected_at <= {parameter} "
                f"ORDER BY collected_at DESC, id DESC LIMIT 1"
            ),
            [surface, self._timestamp_literal(at)],
        )
        if row is None:
            raise SurfaceNotFoundError(surface)
        return decode_json(row["data"])

    def list_stale(self) -> list[SurfaceSnapshot]:
        query = (
            f"SELECT surface, data, collected_at, stale, is_expired "
            f"FROM {self.current_view_name} WHERE stale = TRUE OR is_expired = TRUE ORDER BY surface"
        )
        with managed_connection(self._connection_factory) as connection:
            cursor = connection.cursor()
            cursor.execute(query)
            return [self._row_to_snapshot(row) for row in rows_to_dicts(cursor)]

    def _fetch_one(
        self,
        query_builder: Callable[[str], str],
        params: list[Any],
    ) -> dict[str, Any] | None:
        with managed_connection(self._connection_factory) as connection:
            cursor = connection.cursor()
            cursor.execute(query_builder(placeholder(connection)), params)
            rows = rows_to_dicts(cursor)
            return rows[0] if rows else None

    @staticmethod
    def _timestamp_literal(value: str | datetime) -> str:
        return parse_timestamp(value).isoformat()

    @staticmethod
    def _row_to_snapshot(row: dict[str, Any]) -> SurfaceSnapshot:
        return SurfaceSnapshot(
            surface=str(row["surface"]),
            data=decode_json(row["data"]),
            collected_at=parse_timestamp(row["collected_at"]),
            stale=bool(row["stale"]),
            is_expired=bool(row.get("is_expired", False)),
        )

    @staticmethod
    def _raise_if_stale(snapshot: SurfaceSnapshot, *, allow_stale: bool) -> None:
        if allow_stale:
            return
        if snapshot.stale or snapshot.is_expired:
            raise StaleDataError(
                snapshot.surface,
                snapshot.collected_at,
                stale=snapshot.stale,
                is_expired=snapshot.is_expired,
            )
