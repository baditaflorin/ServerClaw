#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


GRAPH_RUNTIME_DEPENDENCIES = ("pyyaml", "psycopg[binary]", "nats-py")
UV_RUNTIME_FLAGS = ("--isolated", "--no-project")


def _requires_uv_runtime(exc: BaseException) -> bool:
    if isinstance(exc, ModuleNotFoundError):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc)
        return "psycopg is required for postgres" in message or "Missing dependency: PyYAML" in message
    return False


def _load_graph_dependencies(repo_root: Path):
    for candidate in (repo_root / "scripts", repo_root):
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
    if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
        del sys.modules["platform"]

    from platform.graph import DependencyGraphClient
    from platform.ledger import LedgerWriter
    from platform.world_state.workers import publish_refresh_event_best_effort

    return DependencyGraphClient, LedgerWriter, publish_refresh_event_best_effort


def _run_via_uv(
    script_path: Path,
    repo_root: Path,
    event_payload: dict[str, Any] | None,
    dsn: str | None,
    world_state_dsn: str | None,
    ledger_dsn: str | None,
    publish_nats: bool,
) -> dict[str, Any]:
    command = ["uv", "run", *UV_RUNTIME_FLAGS]
    for dependency in GRAPH_RUNTIME_DEPENDENCIES:
        command.extend(["--with", dependency])
    command.extend(
        [
            "python3",
            str(script_path),
            "--repo-path",
            str(repo_root),
        ]
    )
    if event_payload:
        command.extend(["--event-payload", json.dumps(event_payload, sort_keys=True)])
    if dsn:
        command.extend(["--dsn", dsn])
    if world_state_dsn:
        command.extend(["--world-state-dsn", world_state_dsn])
    if ledger_dsn:
        command.extend(["--ledger-dsn", ledger_dsn])
    if not publish_nats:
        command.append("--no-publish-nats")

    result = subprocess.run(command, cwd=script_path.parent, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if result.stdout.strip():
        try:
            payload["result"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return payload


def _write_ledger_event(
    ledger_dsn: str | None,
    payload: dict[str, Any],
    *,
    ledger_writer_cls: Any,
) -> dict[str, Any] | None:
    if not ledger_dsn:
        return None
    writer = ledger_writer_cls(dsn=ledger_dsn, nats_publisher=None)
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
    try:
        DependencyGraphClient, LedgerWriter, publish_refresh_event_best_effort = _load_graph_dependencies(repo_root)
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
    except (ModuleNotFoundError, RuntimeError) as exc:
        if not _requires_uv_runtime(exc):
            raise
        return _run_via_uv(
            repo_root / "config" / "windmill" / "scripts" / "graph" / "propagate-health.py",
            repo_root,
            event_payload,
            dsn,
            world_state_dsn,
            ledger_dsn,
            publish_nats,
        )

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
            ledger_writer_cls=LedgerWriter,
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run ADR 0117 derived health propagation.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--event-payload", default="")
    parser.add_argument("--dsn")
    parser.add_argument("--world-state-dsn")
    parser.add_argument("--ledger-dsn")
    parser.add_argument("--no-publish-nats", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.event_payload) if args.event_payload else None
    print(
        json.dumps(
            main(
                event_payload=payload,
                repo_path=args.repo_path,
                dsn=args.dsn,
                world_state_dsn=args.world_state_dsn,
                ledger_dsn=args.ledger_dsn,
                publish_nats=not args.no_publish_nats,
            ),
            indent=2,
        )
    )
