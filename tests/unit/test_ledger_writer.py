from __future__ import annotations

import importlib.util
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from platform.ledger import LedgerReader, LedgerReplayer, LedgerWriter


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_SQL_PATH = REPO_ROOT / "migrations" / "0011_ledger_schema.sql"
MIGRATION_SCRIPT_PATH = REPO_ROOT / "windmill" / "ledger" / "migrate-audit-log.py"


class FakeIntegrityError(Exception):
    pass


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.description: list[tuple[str]] = []
        self._results: list[Any] = []
        self._index = 0
        self._mode = "generic"

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        normalized = " ".join(sql.split())
        self.connection.queries.append((normalized, params))
        if (
            "ALTER TABLE audit_log RENAME TO audit_log_legacy" in normalized
            or normalized.startswith("DO $$")
            or normalized.startswith("CREATE OR REPLACE VIEW audit_log AS")
        ):
            self.connection.view_statements.append(normalized)
            self._results = []
            self.description = []
            return
        if normalized == "SELECT to_regclass('public.audit_log') IS NOT NULL":
            self.description = [("exists",)]
            self._results = [(self.connection.audit_log_exists,)]
            self._index = 0
            return
        if normalized.startswith("INSERT INTO ledger.events"):
            self._handle_insert(params or ())
            return
        if normalized == "SELECT * FROM audit_log ORDER BY id ASC":
            self._mode = "audit_log"
            self.description = (
                [(key,) for key in self.connection.audit_rows[0].keys()] if self.connection.audit_rows else []
            )
            self._results = [dict(row) for row in self.connection.audit_rows]
            self._index = 0
            return
        if "FROM ledger.events" in normalized:
            self._handle_ledger_select(normalized, params or ())
            return
        raise AssertionError(f"unexpected SQL in test fake: {normalized}")

    def _handle_insert(self, params: tuple[Any, ...]) -> None:
        event_id = str(params[0])
        if event_id in self.connection.event_ids:
            raise FakeIntegrityError(event_id)
        self.connection.event_ids.add(event_id)
        occurred_at = params[2] or f"2026-03-24T00:00:{self.connection.next_id:02d}+00:00"
        row = {
            "id": self.connection.next_id,
            "event_id": event_id,
            "event_type": params[1],
            "occurred_at": occurred_at,
            "actor": params[3],
            "actor_intent_id": params[4],
            "tool_id": params[5],
            "target_kind": params[6],
            "target_id": params[7],
            "before_state": params[8],
            "after_state": params[9],
            "receipt": params[10],
            "metadata": params[11],
        }
        self.connection.rows.append(row)
        self.connection.next_id += 1
        self.description = [(key,) for key in row.keys()]
        self._results = [row]
        self._index = 0

    def _handle_ledger_select(self, normalized: str, params: tuple[Any, ...]) -> None:
        rows = [self._decode_row(row) for row in self.connection.rows]
        if "WHERE actor_intent_id = %s" in normalized:
            actor_intent_id, limit = params
            rows = [row for row in rows if row["actor_intent_id"] == actor_intent_id][: int(limit)]
        elif "WHERE target_kind = %s AND target_id = %s" in normalized:
            target_kind, target_id, *rest = params
            rows = [row for row in rows if row["target_kind"] == target_kind and row["target_id"] == target_id]
            if "occurred_at >= %s" in normalized:
                from_ts = str(rest.pop(0))
                rows = [row for row in rows if str(row["occurred_at"]) >= from_ts]
            if "occurred_at <= %s" in normalized:
                to_ts = str(rest.pop(0))
                rows = [row for row in rows if str(row["occurred_at"]) <= to_ts]
            limit = int(rest.pop(0))
            rows = rows[:limit]
        elif "WHERE occurred_at >= %s AND occurred_at <= %s" in normalized:
            from_ts, to_ts, *rest = params
            rows = [row for row in rows if str(from_ts) <= str(row["occurred_at"]) <= str(to_ts)]
            if "target_kind = %s" in normalized:
                target_kind = rest.pop(0)
                rows = [row for row in rows if row["target_kind"] == target_kind]
            if "target_id = %s" in normalized:
                target_id = rest.pop(0)
                rows = [row for row in rows if row["target_id"] == target_id]
            limit = int(rest.pop(0))
            rows = rows[:limit]
        else:
            raise AssertionError(f"unexpected ledger SELECT in test fake: {normalized}")
        self.description = (
            [(key,) for key in rows[0].keys()]
            if rows
            else [(key,) for key in self._decode_row(self.connection.rows[0]).keys()]
            if self.connection.rows
            else []
        )
        self._results = rows
        self._index = 0

    @staticmethod
    def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        for key in ("before_state", "after_state", "receipt", "metadata"):
            value = decoded.get(key)
            if isinstance(value, str) and value.strip().startswith(("{", "[")):
                decoded[key] = json.loads(value)
        return decoded

    def fetchone(self) -> Any:
        if not self._results:
            return None
        return self._results[0]

    def fetchall(self) -> list[Any]:
        return list(self._results)

    def fetchmany(self, size: int) -> list[Any]:
        batch = self._results[self._index : self._index + size]
        self._index += len(batch)
        return batch


class FakeConnection:
    def __init__(self, *, audit_rows: list[dict[str, Any]] | None = None, audit_log_exists: bool | None = None) -> None:
        self.rows: list[dict[str, Any]] = []
        self.audit_rows = audit_rows or []
        self.audit_log_exists = (audit_rows is not None) if audit_log_exists is None else audit_log_exists
        self.event_ids: set[str] = set()
        self.next_id = 1
        self.commits = 0
        self.closed = False
        self.queries: list[tuple[str, tuple[Any, ...] | None]] = []
        self.view_statements: list[str] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


def load_migration_script():
    spec = importlib.util.spec_from_file_location("test_migrate_audit_log", MIGRATION_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_platform_shim_keeps_stdlib_surface_available() -> None:
    import platform

    assert callable(platform.system)
    assert isinstance(platform.python_version(), str)
    assert hasattr(platform, "__path__")


def test_writer_inserts_event_and_publishes_asynchronously() -> None:
    connection = FakeConnection()
    publisher_started = threading.Event()
    publisher_release = threading.Event()

    def publisher(subject: str, payload: dict[str, Any]) -> None:
        assert subject == "platform.mutation.recorded"
        assert payload["event_type"] == "service.deployed"
        publisher_started.set()
        publisher_release.wait(timeout=1)

    writer = LedgerWriter(connection=connection, nats_publisher=publisher)
    started_at = time.monotonic()
    record = writer.write(
        event_type="service.deployed",
        actor="operator:florin",
        target_kind="service",
        target_id="netbox",
        before_state={"version": "1.0.0"},
        after_state={"version": "1.1.0"},
        metadata={"change": "deploy"},
    )
    elapsed = time.monotonic() - started_at
    publisher_release.set()

    assert elapsed < 0.1
    assert publisher_started.wait(timeout=0.2)
    assert connection.commits == 1
    assert record["event_type"] == "service.deployed"
    assert record["before_state"] == {"version": "1.0.0"}
    assert record["after_state"] == {"version": "1.1.0"}
    assert record["metadata"] == {"change": "deploy"}


def test_writer_adds_session_workspace_metadata_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection()
    monkeypatch.setenv("LV3_SESSION_ID", "test-session")
    monkeypatch.setenv("LV3_SESSION_SLUG", "test-session")
    monkeypatch.setenv("LV3_SESSION_LOCAL_ROOT", "/tmp/lv3/test-session")
    monkeypatch.setenv("LV3_SESSION_NATS_PREFIX", "platform.ws.test-session")
    monkeypatch.setenv("LV3_SESSION_STATE_NAMESPACE", "ws:test-session")

    writer = LedgerWriter(connection=connection, nats_publisher=None)
    record = writer.write(
        event_type="service.deployed",
        actor="operator:florin",
        target_kind="service",
        target_id="netbox",
        metadata={"change": "deploy"},
    )

    assert record["metadata"]["change"] == "deploy"
    assert record["metadata"]["session_workspace"] == {
        "session_id": "test-session",
        "session_slug": "test-session",
        "local_state_root": "/tmp/lv3/test-session",
        "nats_prefix": "platform.ws.test-session",
        "state_namespace": "ws:test-session",
    }


def test_writer_rejects_duplicate_event_id() -> None:
    connection = FakeConnection()
    writer = LedgerWriter(connection=connection, nats_publisher=None)
    event_id = str(uuid.uuid4())

    writer.write(
        event_type="service.deployed",
        actor="operator:florin",
        target_kind="service",
        target_id="netbox",
        event_id=event_id,
    )

    with pytest.raises(FakeIntegrityError):
        writer.write(
            event_type="service.deployed",
            actor="operator:florin",
            target_kind="service",
            target_id="netbox",
            event_id=event_id,
        )


def test_writer_falls_back_to_file_sink(tmp_path: Path) -> None:
    sink_path = tmp_path / "ledger.events.jsonl"
    writer = LedgerWriter(file_path=sink_path, nats_publisher=None)

    record = writer.write(
        event_type="intent.compiled",
        actor="operator:lv3-cli",
        target_kind="service",
        target_id="netbox",
        actor_intent_id="intent:test",
        metadata={"matched_rule_id": "deploy-service"},
    )

    assert record["id"] is None
    assert sink_path.exists()
    persisted = [json.loads(line) for line in sink_path.read_text(encoding="utf-8").splitlines()]
    assert persisted == [record]


def test_writer_accepts_speculative_execution_event_types() -> None:
    connection = FakeConnection()
    writer = LedgerWriter(connection=connection, nats_publisher=None)

    record = writer.write(
        event_type="execution.speculative_committed",
        actor="scheduler:test",
        target_kind="workflow",
        target_id="rotate-netbox-db-password",
        actor_intent_id="intent-spec",
        metadata={"conflict_detected": False},
    )

    assert record["event_type"] == "execution.speculative_committed"


def test_writer_maps_legacy_mutation_audit_events() -> None:
    connection = FakeConnection()
    writer = LedgerWriter(connection=connection, nats_publisher=None)

    record = writer.write_mutation_audit_event(
        {
            "ts": "2026-03-24T08:00:00Z",
            "actor": {"class": "automation", "id": "ansible-playbook"},
            "surface": "ansible",
            "action": "deploy.netbox",
            "target": "netbox",
            "outcome": "success",
            "correlation_id": "ansible:test",
            "evidence_ref": "receipts/live-applies/test.json",
        }
    )

    assert record["event_type"] == "execution.completed"
    assert record["tool_id"] == "ansible"
    assert record["target_kind"] == "service"
    assert record["metadata"]["legacy_action"] == "deploy.netbox"
    assert record["metadata"]["state_capture"] is False


def test_reader_and_replayer_return_ordered_events_and_project_state() -> None:
    connection = FakeConnection()
    writer = LedgerWriter(connection=connection, nats_publisher=None)
    writer.write(
        event_type="service.deployed",
        occurred_at="2026-03-24T00:00:00+00:00",
        actor="operator:florin",
        target_kind="service",
        target_id="netbox",
        after_state={"version": "1.0.0"},
    )
    writer.write(
        event_type="service.config_changed",
        occurred_at="2026-03-24T01:00:00+00:00",
        actor="operator:florin",
        target_kind="service",
        target_id="netbox",
        before_state={"version": "1.0.0"},
        after_state={"version": "1.1.0"},
    )

    reader = LedgerReader(connection=connection)
    events = reader.events_by_target(target_kind="service", target_id="netbox", limit=10)
    assert [event["event_type"] for event in events] == ["service.deployed", "service.config_changed"]

    replayer = LedgerReplayer(reader=reader)
    assert replayer.project_state("service:netbox", at="2026-03-24T00:30:00+00:00") == {"version": "1.0.0"}
    assert replayer.project_state("service:netbox", at="2026-03-24T02:00:00+00:00") == {"version": "1.1.0"}
    with pytest.raises(NotImplementedError):
        replayer.project_state("host:proxmox_florin", at="2026-03-24T02:00:00+00:00")


def test_migration_helper_moves_legacy_rows_and_installs_view() -> None:
    module = load_migration_script()
    connection = FakeConnection(
        audit_rows=[
            {
                "id": 1,
                "ts": "2026-03-23T10:00:00Z",
                "actor_class": "operator",
                "actor_id": "ops",
                "surface": "manual",
                "action": "document.manual_change",
                "target": "proxmox_florin",
                "outcome": "success",
                "correlation_id": "legacy:1",
                "evidence_ref": "docs/runbooks/mutation-audit-log.md",
            },
            {
                "id": 2,
                "ts": "2026-03-23T11:00:00Z",
                "actor_class": "automation",
                "actor_id": "ansible-playbook",
                "surface": "ansible",
                "action": "deploy.netbox",
                "target": "netbox",
                "outcome": "failure",
                "correlation_id": "legacy:2",
                "evidence_ref": "",
            },
        ]
    )

    result = module.migrate_audit_log(connection=connection, batch_size=1)

    assert result == {"migrated_rows": 2, "batches": 2, "legacy_view_applied": True}
    assert len(connection.rows) == 2
    assert any("CREATE OR REPLACE VIEW audit_log AS" in statement for statement in connection.view_statements)
    assert json.loads(connection.rows[0]["metadata"])["legacy_row_id"] == 1
    assert connection.rows[1]["event_type"] == "execution.failed"


def test_migration_helper_installs_view_when_no_sql_audit_source_exists() -> None:
    module = load_migration_script()
    connection = FakeConnection()

    result = module.migrate_audit_log(connection=connection, batch_size=1)

    assert result == {"migrated_rows": 0, "batches": 0, "legacy_view_applied": True}
    assert connection.rows == []
    assert any("CREATE OR REPLACE VIEW audit_log AS" in statement for statement in connection.view_statements)


def test_migration_sql_declares_append_only_trigger() -> None:
    sql = MIGRATION_SQL_PATH.read_text(encoding="utf-8")

    assert "BEFORE UPDATE OR DELETE ON ledger.events" in sql
    assert "ledger.events is append-only" in sql
