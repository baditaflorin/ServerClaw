from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from platform.idempotency import IdempotencyStore, compute_idempotency_key


def test_compute_idempotency_key_normalises_volatile_fields() -> None:
    now = datetime(2026, 3, 25, 10, 37, tzinfo=UTC)
    first = compute_idempotency_key(
        "rotate-secret",
        "keycloak",
        {
            "service": "keycloak",
            "request_id": str(uuid.uuid4()),
            "submitted_at": "2026-03-25T10:36:00Z",
            "nested": {"trace_id": str(uuid.uuid4()), "ts": "2026-03-25T10:37:11Z"},
        },
        "agent/rotation",
        now=now,
    )
    second = compute_idempotency_key(
        "rotate-secret",
        "keycloak",
        {
            "nested": {"trace_id": str(uuid.uuid4()), "ts": "2026-03-25T10:39:59Z"},
            "service": "keycloak",
            "request_id": str(uuid.uuid4()),
        },
        "agent/rotation",
        now=now,
    )

    assert first == second


def test_file_store_returns_completed_hits_and_retries_after_failure(tmp_path: Path) -> None:
    clock = lambda: datetime(2026, 3, 25, 9, 0, tzinfo=UTC)
    store = IdempotencyStore(repo_root=tmp_path, now_fn=clock)

    created = store.claim(
        idempotency_key="idem:test",
        workflow_id="converge-netbox",
        actor_id="operator:lv3-cli",
        actor_intent_id="intent-1",
        target_service_id="netbox",
    )
    assert created.action == "created"

    in_flight = store.claim(
        idempotency_key="idem:test",
        workflow_id="converge-netbox",
        actor_id="operator:lv3-cli",
        actor_intent_id="intent-2",
        target_service_id="netbox",
    )
    assert in_flight.action == "in_flight"

    store.complete("idem:test", status="completed", result={"status": "ok"}, job_id="job-1")
    completed = store.claim(
        idempotency_key="idem:test",
        workflow_id="converge-netbox",
        actor_id="operator:lv3-cli",
        actor_intent_id="intent-3",
        target_service_id="netbox",
    )
    assert completed.action == "completed"
    assert completed.record.windmill_job_id == "job-1"
    assert completed.record.result == {"status": "ok"}

    store.complete("idem:test", status="failed", result={"error": "boom"}, job_id="job-2")
    retried = store.claim(
        idempotency_key="idem:test",
        workflow_id="converge-netbox",
        actor_id="operator:lv3-cli",
        actor_intent_id="intent-4",
        target_service_id="netbox",
    )
    assert retried.action == "created"
    assert retried.record.actor_intent_id == "intent-4"
