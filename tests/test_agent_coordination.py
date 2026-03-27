from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from platform.agent import AgentCoordinationStore


def build_store(tmp_path: Path, *, now: datetime | None = None) -> AgentCoordinationStore:
    fixed_now = now or datetime(2026, 3, 25, 9, 0, tzinfo=UTC)
    return AgentCoordinationStore(
        repo_root=tmp_path,
        nats_url=None,
        state_file=tmp_path / "agent-coordination.json",
        event_publisher=None,
        now=lambda: fixed_now,
    )


def test_publish_snapshot_and_filter_by_target(tmp_path: Path) -> None:
    store = build_store(tmp_path)
    store.publish(
        store.build_entry(
            agent_id="agent/observation-loop",
            context_id="ctx-1",
            session_label="observation-loop ctx-1",
            current_phase="executing",
            current_target="service:grafana",
            current_workflow_id="platform-observation-loop",
            held_locks=["service:grafana"],
            progress_pct=0.5,
        )
    )
    store.publish(
        store.build_entry(
            agent_id="agent/triage-loop",
            context_id="ctx-2",
            session_label="triage-loop ctx-2",
            current_phase="blocked",
            current_target="service:keycloak",
            status="blocked",
            blocked_reason="waiting for approval",
        )
    )

    snapshot = store.snapshot()

    assert snapshot["summary"]["count"] == 2
    assert snapshot["summary"]["active"] == 1
    assert snapshot["summary"]["blocked"] == 1
    assert [entry.agent_id for entry in store.read_by_target("service:grafana")] == ["agent/observation-loop"]


def test_expired_entries_are_pruned_from_file_state(tmp_path: Path) -> None:
    started = datetime(2026, 3, 25, 9, 0, tzinfo=UTC)
    writer = build_store(tmp_path, now=started)
    writer.publish(
        writer.build_entry(
            agent_id="agent/observation-loop",
            context_id="ctx-expired",
            session_label="expired",
            current_phase="executing",
        )
    )

    reader = build_store(tmp_path, now=started + timedelta(minutes=10))

    assert reader.read_all() == []


def test_session_finish_deletes_entry(tmp_path: Path) -> None:
    store = build_store(tmp_path)

    with store.session(
        agent_id="agent/observation-loop",
        context_id="ctx-3",
        session_label="observation-loop ctx-3",
        current_phase="bootstrapping",
        current_target="batch:findings",
    ) as session:
        session.transition("executing", current_target="service:grafana", progress_pct=0.25)
        assert store.snapshot()["summary"]["count"] == 1

    assert store.snapshot()["summary"]["count"] == 0
