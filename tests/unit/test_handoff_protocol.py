from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from repo_package_loader import load_repo_package


HANDOFF_MODULE = load_repo_package(
    "lv3_handoff_test",
    Path(__file__).resolve().parents[2] / "platform" / "handoff",
)
HandoffClient = HANDOFF_MODULE.HandoffClient
HandoffMessage = HANDOFF_MODULE.HandoffMessage
HandoffResponse = HANDOFF_MODULE.HandoffResponse
HandoffStore = HANDOFF_MODULE.HandoffStore
InMemoryHandoffBus = HANDOFF_MODULE.InMemoryHandoffBus


class RecordingLedgerWriter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write(self, **payload: Any) -> dict[str, Any]:
        self.events.append(payload)
        return payload


def build_store(tmp_path: Path) -> HandoffStore:
    store = HandoffStore(dsn=f"sqlite:///{tmp_path / 'handoffs.sqlite3'}")
    store.ensure_schema()
    return store


def test_store_round_trip_records_acceptance(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    message = HandoffMessage(
        handoff_id="handoff-001",
        from_agent="agent/triage-loop",
        to_agent="operator",
        task_id="incident:001",
        subject="Investigate NetBox alert",
        payload={"severity": "high"},
        handoff_type="escalate",
        requires_accept=True,
    )

    created = store.record_send(message)
    updated = store.record_response(
        HandoffResponse(
            handoff_id="handoff-001",
            from_agent="operator",
            to_agent="agent/triage-loop",
            decision="accept",
            estimated_completion_seconds=300,
        )
    )

    assert created.status == "pending"
    assert updated.status == "accepted"
    assert updated.response_decision == "accept"
    assert updated.estimated_completion_seconds == 300
    listed = store.list_transfers(task_id="incident:001")
    assert [transfer.handoff_id for transfer in listed] == ["handoff-001"]


def test_client_retries_busy_then_accepts(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    bus = InMemoryHandoffBus()
    attempts: dict[str, int] = {}

    def handler(message: Any) -> Any:
        attempts[message.handoff_id] = attempts.get(message.handoff_id, 0) + 1
        if attempts[message.handoff_id] == 1:
            return HandoffResponse(
                handoff_id=message.handoff_id,
                from_agent="agent/runbook-executor",
                to_agent=message.from_agent,
                decision="refuse",
                reason="busy",
            )
        return HandoffResponse(
            handoff_id=message.handoff_id,
            from_agent="agent/runbook-executor",
            to_agent=message.from_agent,
            decision="accept",
        )

    bus.register("agent/runbook-executor", handler)
    ledger = RecordingLedgerWriter()
    client = HandoffClient(store=store, bus=bus, ledger_writer=ledger, sleep_fn=lambda _seconds: None)

    transfer = client.send(
        HandoffMessage(
            handoff_id="handoff-002",
            from_agent="agent/triage-loop",
            to_agent="agent/runbook-executor",
            task_id="incident:002",
            subject="Execute certificate renewal runbook",
            payload={"runbook_id": "renew-tls-certificate"},
            requires_accept=True,
            max_retries=1,
            backoff_seconds=0,
        )
    )

    assert transfer.status == "accepted"
    assert attempts["handoff-002"] == 2
    assert [event["event_type"] for event in ledger.events] == [
        "handoff.transfer_recorded",
        "handoff.accepted",
    ]


def test_client_timeout_escalates_to_operator(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    ledger = RecordingLedgerWriter()
    notifications: list[tuple[str, str | None]] = []
    client = HandoffClient(
        store=store,
        bus=InMemoryHandoffBus(),
        ledger_writer=ledger,
        operator_notifier=lambda transfer, reason: notifications.append((transfer.handoff_id, reason)),
        sleep_fn=lambda _seconds: None,
    )

    transfer = client.send(
        HandoffMessage(
            handoff_id="handoff-003",
            from_agent="agent/observation-loop",
            to_agent="agent/runbook-executor",
            task_id="finding:003",
            subject="Investigate stale probe",
            payload={"service": "netbox"},
            requires_accept=True,
            timeout_seconds=0,
            fallback="operator",
        )
    )

    assert transfer.status == "escalated"
    assert notifications == [("handoff-003", "acceptance_timeout")]
    assert [event["event_type"] for event in ledger.events] == [
        "handoff.transfer_recorded",
        "handoff.timed_out",
        "handoff.escalated_to_operator",
    ]


def test_handoff_load_burst_completes_without_duplicates(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    bus = InMemoryHandoffBus()
    ledger = RecordingLedgerWriter()
    client = HandoffClient(store=store, bus=bus, ledger_writer=ledger, sleep_fn=lambda _seconds: None)

    def handler(message: Any) -> Any:
        return HandoffResponse(
            handoff_id=message.handoff_id,
            from_agent="agent/runbook-executor",
            to_agent=message.from_agent,
            decision="accept",
            estimated_completion_seconds=15,
        )

    bus.register("agent/runbook-executor", handler)

    def send_one(index: int) -> dict[str, Any]:
        transfer = client.send(
            HandoffMessage(
                handoff_id=f"handoff-load-{index:03d}",
                from_agent="agent/triage-loop",
                to_agent="agent/runbook-executor",
                task_id=f"incident:{index:03d}",
                subject=f"Run remediation {index}",
                payload={"index": index},
                requires_accept=True,
            )
        )
        return transfer.to_dict()

    with ThreadPoolExecutor(max_workers=16) as executor:
        transfers = list(executor.map(send_one, range(120)))

    assert len(transfers) == 120
    assert len({transfer["handoff_id"] for transfer in transfers}) == 120
    assert {transfer["status"] for transfer in transfers} == {"accepted"}
    persisted = store.list_transfers(limit=200)
    assert len(persisted) == 120
    event_types = [event["event_type"] for event in ledger.events]
    assert event_types.count("handoff.transfer_recorded") == 120
    assert event_types.count("handoff.accepted") == 120
