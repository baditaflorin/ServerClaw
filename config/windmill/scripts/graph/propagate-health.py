#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from platform.graph import DependencyGraphClient
from platform.ledger import LedgerWriter
from platform.world_state.workers import publish_refresh_event_best_effort


def _write_ledger_event(ledger_dsn: str | None, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not ledger_dsn:
        return None
    writer = LedgerWriter(dsn=ledger_dsn, nats_publisher=None)
    return writer.write(
        event_type="graph.health_propagated",
        actor="automation:windmill-graph-health",
        tool_id="windmill.graph.propagate-health",
        target_kind="service",
        target_id=str(payload["service_id"]),
        after_state=payload,
        metadata={
            "cause_node": payload["cause_node"],
            "cause_status": payload["cause_status"],
            "path": payload["path"],
        },
    )


def main(
    event_payload: dict[str, Any] | None = None,
    repo_path: str = "/srv/proxmox_florin_server",
    dsn: str | None = None,
    world_state_dsn: str | None = None,
    ledger_dsn: str | None = None,
    publish_nats: bool = True,
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    payload = event_payload or {}
    if payload and payload.get("surface") not in {None, "service_health"}:
        return {"status": "skipped", "reason": "world_state event is not for service_health"}

    client = DependencyGraphClient(
        dsn=dsn,
        world_state_dsn=world_state_dsn or dsn,
    )
    health_snapshot = client.world_state_client.get("service_health", allow_stale=True) if client.world_state_client else {}
    services = health_snapshot.get("services", []) if isinstance(health_snapshot, dict) else []
    degraded_sources = [
        service
        for service in services
        if isinstance(service, dict) and str(service.get("status")) in {"degraded", "down"}
    ]

    derived_events: list[dict[str, Any]] = []
    for service in degraded_sources:
        service_id = service.get("service_id")
        status = service.get("status")
        if not isinstance(service_id, str) or not isinstance(status, str):
            continue
        derived_events.extend(client.health_propagation(f"service:{service_id}", status=status))

    emitted_results: list[dict[str, Any]] = []
    ledger_results: list[dict[str, Any]] = []
    for item in derived_events:
        event = {
            "node": item["node"],
            "service_id": item["service_id"],
            "derived_status": item["derived_status"],
            "cause_node": item["cause_node"],
            "cause_status": item["cause_status"],
            "path": item["path"],
        }
        if publish_nats:
            emitted_results.append(publish_refresh_event_best_effort("derived_health_degraded", event))
        ledger_record = _write_ledger_event(
            ledger_dsn or os.environ.get("LV3_LEDGER_DSN", "").strip() or None,
            event,
        )
        if ledger_record is not None:
            ledger_results.append(ledger_record)

    return {
        "status": "ok",
        "source_event": payload or None,
        "degraded_source_count": len(degraded_sources),
        "derived_event_count": len(derived_events),
        "derived_events": derived_events,
        "publish_results": emitted_results,
        "ledger_records": ledger_results,
    }
