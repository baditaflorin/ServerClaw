from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from platform.agent import AgentStateClient, AgentStateLimitError


def prepare_agent_state_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE agent_state (
            state_id TEXT,
            agent_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            context_id TEXT,
            written_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            UNIQUE(agent_id, task_id, key)
        )
        """
    )
    connection.commit()
    connection.close()
    return path


def build_client(
    db_path: Path,
    *,
    now: datetime | None = None,
    publisher=None,
    max_keys: int = 100,
    max_value_bytes: int = 64 * 1024,
) -> AgentStateClient:
    fixed_now = now or datetime(2026, 3, 24, 10, 0, tzinfo=UTC)
    return AgentStateClient(
        agent_id="agent/triage-loop",
        task_id="incident:inc-2026-03-24-001",
        dsn=f"sqlite:///{db_path}",
        now=lambda: fixed_now,
        checkpoint_publisher=publisher,
        max_keys=max_keys,
        max_value_bytes=max_value_bytes,
    )


def test_write_and_read_persist_across_clients(tmp_path: Path) -> None:
    db_path = prepare_agent_state_db(tmp_path / "agent-state.sqlite3")
    writer = build_client(db_path)
    reader = build_client(db_path)

    writer.write("hypothesis.1", {"id": "recent-deployment", "confidence": 0.85})

    assert reader.read("hypothesis.1") == {"id": "recent-deployment", "confidence": 0.85}


def test_expired_rows_are_filtered_and_purgeable(tmp_path: Path) -> None:
    db_path = prepare_agent_state_db(tmp_path / "agent-state.sqlite3")
    started = datetime(2026, 3, 24, 10, 0, tzinfo=UTC)
    build_client(db_path, now=started).write("context_summary.short", {"cached": True}, ttl_hours=1)
    expired_client = build_client(db_path, now=started + timedelta(hours=2))

    assert expired_client.read("context_summary.short") is None
    assert expired_client.purge_expired() == 1


def test_checkpoint_emits_digest_and_verify_handoff_matches(tmp_path: Path) -> None:
    db_path = prepare_agent_state_db(tmp_path / "agent-state.sqlite3")
    published: list[tuple[str, dict[str, object]]] = []
    client = build_client(db_path, publisher=lambda subject, payload: published.append((subject, payload)))

    checkpoint = client.checkpoint(
        {
            "last_completed_step": "renew-cert",
            "resume_at": "verify-health",
        }
    )
    verification = build_client(db_path).validate_handoff(str(checkpoint["state_digest"]))

    assert checkpoint["keys"] == ["last_completed_step", "resume_at"]
    assert published[0][0] == "platform.agent.state_checkpoint"
    assert verification.matched is True
    assert verification.key_count == 2


def test_write_rejects_large_values(tmp_path: Path) -> None:
    db_path = prepare_agent_state_db(tmp_path / "agent-state.sqlite3")
    client = build_client(db_path, max_value_bytes=32)

    with pytest.raises(AgentStateLimitError):
        client.write("oversized", {"payload": "x" * 64})


def test_write_enforces_key_limit(tmp_path: Path) -> None:
    db_path = prepare_agent_state_db(tmp_path / "agent-state.sqlite3")
    client = build_client(db_path, max_keys=1)

    client.write("first", {"ok": True})
    with pytest.raises(AgentStateLimitError):
        client.write("second", {"ok": False})
