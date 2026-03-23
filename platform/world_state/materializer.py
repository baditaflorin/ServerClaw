from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ._db import (
    ConnectionFactory,
    connection_kind,
    create_connection_factory,
    decode_json,
    isoformat,
    managed_connection,
    placeholder,
    rows_to_dicts,
    utc_now,
)


CURRENT_VIEW_NAME = "world_state.current_view"
SQLITE_CURRENT_VIEW_NAME = "world_state_current_view"
SNAPSHOTS_TABLE_NAME = "world_state.snapshots"
SQLITE_SNAPSHOTS_TABLE_NAME = "world_state_snapshots"


@dataclass(frozen=True)
class SurfaceDefinition:
    surface: str
    refresh_interval_seconds: int
    stale_threshold_seconds: int
    summary: str


SURFACE_DEFINITIONS: dict[str, SurfaceDefinition] = {
    "proxmox_vms": SurfaceDefinition("proxmox_vms", 60, 300, "Proxmox VM inventory and runtime state"),
    "service_health": SurfaceDefinition("service_health", 30, 120, "Service health probe rollup"),
    "container_inventory": SurfaceDefinition("container_inventory", 60, 300, "Runtime container inventory"),
    "netbox_topology": SurfaceDefinition("netbox_topology", 300, 1800, "NetBox topology snapshot"),
    "dns_records": SurfaceDefinition("dns_records", 300, 1800, "Published DNS records"),
    "tls_cert_expiry": SurfaceDefinition("tls_cert_expiry", 3600, 21600, "TLS certificate expiry inventory"),
    "opentofu_drift": SurfaceDefinition("opentofu_drift", 900, 3600, "OpenTofu drift summary"),
    "openbao_secret_expiry": SurfaceDefinition("openbao_secret_expiry", 300, 1800, "OpenBao lease and secret expiry"),
    "maintenance_windows": SurfaceDefinition("maintenance_windows", 60, 300, "Active maintenance windows"),
}


EventPublisher = Callable[[str, dict[str, Any]], Any]


def surface_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("items", "services", "containers", "records", "certificates", "leases", "active_windows"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return len(candidate)
        summary = payload.get("summary")
        if isinstance(summary, dict):
            for key in ("total", "count", "service_count", "container_count", "record_count", "lease_count"):
                value = summary.get(key)
                if isinstance(value, int):
                    return value
    return 0


def build_refresh_event(surface: str, *, collected_at: datetime, stale: bool, payload: Any) -> dict[str, Any]:
    definition = SURFACE_DEFINITIONS[surface]
    return {
        "surface": surface,
        "summary": definition.summary,
        "collected_at": isoformat(collected_at),
        "stale": stale,
        "record_count": surface_count(payload),
        "refresh_interval_seconds": definition.refresh_interval_seconds,
        "stale_threshold_seconds": definition.stale_threshold_seconds,
    }


def materialize_surface(
    surface: str,
    payload: Any,
    *,
    stale: bool = False,
    collected_at: datetime | None = None,
    connection_factory: ConnectionFactory | None = None,
    dsn: str | None = None,
    event_publisher: EventPublisher | None = None,
) -> dict[str, Any]:
    if surface not in SURFACE_DEFINITIONS:
        raise ValueError(f"Unknown world-state surface '{surface}'")

    collected = collected_at or utc_now()
    factory = connection_factory or create_connection_factory(dsn)
    event = build_refresh_event(surface, collected_at=collected, stale=stale, payload=payload)

    with managed_connection(factory) as connection:
        kind = connection_kind(connection)
        snapshot_table = SQLITE_SNAPSHOTS_TABLE_NAME if kind == "sqlite" else SNAPSHOTS_TABLE_NAME
        current_view = SQLITE_CURRENT_VIEW_NAME if kind == "sqlite" else CURRENT_VIEW_NAME
        parameter = placeholder(connection)
        cursor = connection.cursor()
        cursor.execute(
            f"INSERT INTO {snapshot_table} (surface, collected_at, data, stale) VALUES ({parameter}, {parameter}, {parameter}, {parameter})",
            [surface, collected.isoformat(), json.dumps(payload), stale],
        )
        if kind == "sqlite":
            cursor.execute(f"DELETE FROM {current_view} WHERE surface = {parameter}", [surface])
            is_expired = False
            cursor.execute(
                f"INSERT INTO {current_view} (surface, data, collected_at, stale, is_expired) VALUES ({parameter}, {parameter}, {parameter}, {parameter}, {parameter})",
                [surface, json.dumps(payload), collected.isoformat(), stale, is_expired],
            )
            connection.commit()
        else:
            connection.commit()
            cursor.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {current_view}")
            connection.commit()

    if event_publisher is not None:
        event_publisher("world_state.refreshed", event)
    return event


def current_view_rows(
    *,
    connection_factory: ConnectionFactory | None = None,
    dsn: str | None = None,
) -> list[dict[str, Any]]:
    factory = connection_factory or create_connection_factory(dsn)
    with managed_connection(factory) as connection:
        current_view = SQLITE_CURRENT_VIEW_NAME if connection_kind(connection) == "sqlite" else CURRENT_VIEW_NAME
        cursor = connection.cursor()
        cursor.execute(
            f"SELECT surface, data, collected_at, stale, is_expired FROM {current_view} ORDER BY surface"
        )
        rows = rows_to_dicts(cursor)
    for row in rows:
        row["data"] = decode_json(row["data"])
    return rows
