from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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


class WorldStateUnavailable(WorldStateError):
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
        repo_root: Path | str | None = None,
        *,
        dsn: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        current_view_name: str = "world_state.current_view",
        snapshots_table_name: str = "world_state.snapshots",
    ):
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
        self._dsn = dsn
        self._connection_factory = connection_factory
        self.current_view_name = current_view_name
        self.snapshots_table_name = snapshots_table_name

    def get(self, surface: str, *, allow_stale: bool = False) -> Any:
        snapshot = self.get_snapshot(surface, allow_stale=allow_stale)
        return snapshot.data

    def get_snapshot(self, surface: str, *, allow_stale: bool = False) -> SurfaceSnapshot:
        if self._uses_repo_snapshot_mode():
            snapshot = self._load_repo_snapshot(surface)
            self._raise_if_stale(snapshot, allow_stale=allow_stale)
            return snapshot
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
        with managed_connection(self._resolved_connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(query)
            return [self._row_to_snapshot(row) for row in rows_to_dicts(cursor)]

    def _fetch_one(
        self,
        query_builder: Callable[[str], str],
        params: list[Any],
    ) -> dict[str, Any] | None:
        with managed_connection(self._resolved_connection_factory()) as connection:
            cursor = connection.cursor()
            cursor.execute(query_builder(placeholder(connection)), params)
            rows = rows_to_dicts(cursor)
            return rows[0] if rows else None

    def _resolved_connection_factory(self) -> ConnectionFactory:
        if self._connection_factory is not None:
            return self._connection_factory
        return create_connection_factory(self._dsn)

    def _uses_repo_snapshot_mode(self) -> bool:
        if self._connection_factory is not None:
            return False
        if (self._dsn or "").strip():
            return False
        return not os.environ.get("WORLD_STATE_DSN", "").strip()

    def _load_repo_snapshot(self, surface: str) -> SurfaceSnapshot:
        env_path = os.environ.get(f"LV3_WORLD_STATE_{surface.upper()}_FILE", "").strip()
        path = Path(env_path).expanduser() if env_path else self.repo_root / ".local" / "state" / "world-state" / f"{surface}.json"
        if not path.exists():
            raise WorldStateUnavailable(f"World-state surface '{surface}' is unavailable at {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        stale = bool(payload.get("stale")) if isinstance(payload, dict) else False
        is_expired = bool(payload.get("is_expired")) if isinstance(payload, dict) else False
        collected_at_value = payload.get("collected_at") if isinstance(payload, dict) else None
        collected_at = parse_timestamp(str(collected_at_value)) if collected_at_value else datetime.fromtimestamp(path.stat().st_mtime)
        return SurfaceSnapshot(
            surface=surface,
            data=payload,
            collected_at=collected_at,
            stale=stale,
            is_expired=is_expired,
        )

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
