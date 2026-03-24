from __future__ import annotations

import datetime as dt
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from ._common import (
    REPO_ROOT,
    dumps_jsonb,
    load_event_type_registry,
    load_module_from_repo,
    normalize_event_row,
    normalize_timestamp,
    resolve_connection,
)


def _default_nats_publisher(subject: str, payload: dict[str, Any]) -> None:
    nats_url = os.environ.get("LV3_LEDGER_NATS_URL", "").strip() or os.environ.get("LV3_NATS_URL", "").strip()
    if not nats_url:
        return
    drift_lib = load_module_from_repo(REPO_ROOT / "scripts" / "drift_lib.py", "lv3_ledger_drift_lib")
    drift_lib.publish_nats_events(
        [{"subject": subject, "payload": payload}],
        nats_url=nats_url,
        credentials=None,
    )


def _publish_async(
    publisher: Callable[[str, dict[str, Any]], None] | None,
    subject: str,
    payload: dict[str, Any],
) -> None:
    if publisher is None:
        return

    def runner() -> None:
        try:
            publisher(subject, payload)
        except Exception:
            return

    thread = threading.Thread(target=runner, name="ledger-event-publisher", daemon=True)
    thread.start()


def derive_target_kind(*, surface: str | None = None, action: str | None = None, target: str) -> str:
    lowered_target = target.lower()
    lowered_action = (action or "").lower()
    lowered_surface = (surface or "").lower()
    if "cert" in lowered_target or "cert" in lowered_action:
        return "cert"
    if any(token in lowered_target for token in ("secret", "token", "approle")) or any(
        token in lowered_action for token in ("secret", "token", "approle", "policy")
    ):
        return "secret"
    if lowered_target.startswith("vm-") or lowered_target.startswith("vm/") or lowered_target.startswith("vmid:"):
        return "vm"
    if lowered_target in {"proxmox_florin", "proxmox-host-lv3"} or "host" in lowered_target:
        return "host"
    if lowered_surface in {"windmill", "command-catalog"}:
        return "workflow"
    return "service"


def mutation_audit_event_type(event: dict[str, Any]) -> str:
    outcome = str(event.get("outcome") or "").strip().lower()
    if outcome == "success":
        return "execution.completed"
    if outcome == "failure":
        return "execution.failed"
    if outcome == "rejected":
        return "execution.aborted"
    raise ValueError(f"unsupported legacy mutation audit outcome: {outcome}")


def mutation_audit_metadata(event: dict[str, Any]) -> dict[str, Any]:
    actor = event.get("actor") or {}
    return {
        "legacy_event": True,
        "legacy_actor_class": actor.get("class"),
        "legacy_surface": event.get("surface"),
        "legacy_action": event.get("action"),
        "legacy_outcome": event.get("outcome"),
        "legacy_correlation_id": event.get("correlation_id"),
        "legacy_evidence_ref": event.get("evidence_ref"),
        "state_capture": False,
    }


ALLOWED_EVENT_TYPES = frozenset(load_event_type_registry())


class LedgerWriter:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        connection: Any = None,
        connect: Callable[[str], Any] | None = None,
        event_types_path=None,
        nats_publisher: Callable[[str, dict[str, Any]], None] | None = _default_nats_publisher,
        publish_subject: str = "platform.ledger.event_written",
        file_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self._dsn = dsn
        self._connection = connection
        self._connect = connect
        self._allowed_event_types = set(load_event_type_registry(event_types_path) if event_types_path else ALLOWED_EVENT_TYPES)
        self._nats_publisher = nats_publisher
        self._publish_subject = publish_subject
        self._file_path = self._resolve_file_path(file_path)

    @staticmethod
    def _resolve_file_path(file_path: str | os.PathLike[str] | None) -> Path | None:
        if file_path is not None:
            return Path(file_path).expanduser()
        candidate = os.environ.get("LV3_LEDGER_FILE", "").strip()
        if not candidate or candidate.lower() == "off":
            return None
        return Path(candidate).expanduser()

    def _write_file_record(self, record: dict[str, Any]) -> dict[str, Any]:
        assert self._file_path is not None
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._file_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def write(
        self,
        *,
        event_type: str,
        actor: str,
        target_kind: str,
        target_id: str,
        actor_intent_id: str | None = None,
        tool_id: str | None = None,
        before_state: Any = None,
        after_state: Any = None,
        receipt: Any = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: dt.datetime | str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        event_type = str(event_type).strip()
        actor = str(actor).strip()
        target_kind = str(target_kind).strip()
        target_id = str(target_id).strip()
        if event_type not in self._allowed_event_types:
            raise ValueError(f"unsupported ledger event type: {event_type}")
        if not actor:
            raise ValueError("actor must be a non-empty string")
        if not target_kind:
            raise ValueError("target_kind must be a non-empty string")
        if not target_id:
            raise ValueError("target_id must be a non-empty string")

        resolved_event_id = event_id or str(uuid.uuid4())
        resolved_metadata = dict(metadata or {})
        resolved_occurred_at = normalize_timestamp(occurred_at)
        resolved_dsn = (self._dsn or os.environ.get("LV3_LEDGER_DSN", "")).strip()
        if self._connection is None and not resolved_dsn and self._file_path is not None:
            record = {
                "id": None,
                "event_id": resolved_event_id,
                "event_type": event_type,
                "occurred_at": resolved_occurred_at or dt.datetime.now(dt.timezone.utc).isoformat(),
                "actor": actor,
                "actor_intent_id": actor_intent_id,
                "tool_id": tool_id,
                "target_kind": target_kind,
                "target_id": target_id,
                "before_state": before_state,
                "after_state": after_state,
                "receipt": receipt,
                "metadata": resolved_metadata,
            }
            self._write_file_record(record)
            _publish_async(self._nats_publisher, self._publish_subject, record)
            return record

        connection, owned_connection = resolve_connection(
            dsn=self._dsn,
            connection=self._connection,
            connect=self._connect,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ledger.events (
                        event_id,
                        event_type,
                        occurred_at,
                        actor,
                        actor_intent_id,
                        tool_id,
                        target_kind,
                        target_id,
                        before_state,
                        after_state,
                        receipt,
                        metadata
                    )
                    VALUES (
                        %s,
                        %s,
                        COALESCE(%s, now()),
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s::jsonb,
                        %s::jsonb,
                        %s::jsonb,
                        %s::jsonb
                    )
                    RETURNING
                        id,
                        event_id,
                        event_type,
                        occurred_at,
                        actor,
                        actor_intent_id,
                        tool_id,
                        target_kind,
                        target_id,
                        before_state,
                        after_state,
                        receipt,
                        metadata
                    """,
                    (
                        resolved_event_id,
                        event_type,
                        resolved_occurred_at,
                        actor,
                        actor_intent_id,
                        tool_id,
                        target_kind,
                        target_id,
                        dumps_jsonb(before_state),
                        dumps_jsonb(after_state),
                        dumps_jsonb(receipt),
                        dumps_jsonb(resolved_metadata),
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        finally:
            if owned_connection:
                connection.close()

        if row is None:
            raise RuntimeError("ledger insert returned no row")
        record = normalize_event_row(cursor, row)
        _publish_async(self._nats_publisher, self._publish_subject, record)
        return record

    def write_mutation_audit_event(self, event: dict[str, Any]) -> dict[str, Any]:
        actor = event.get("actor") or {}
        actor_class = str(actor.get("class") or "").strip()
        actor_id = str(actor.get("id") or "").strip()
        if not actor_class or not actor_id:
            raise ValueError("legacy mutation audit event must include actor.class and actor.id")
        target = str(event.get("target") or "").strip()
        if not target:
            raise ValueError("legacy mutation audit event must include target")
        return self.write(
            event_type=mutation_audit_event_type(event),
            occurred_at=str(event["ts"]) if event.get("ts") else None,
            actor=f"{actor_class}:{actor_id}",
            tool_id=str(event.get("surface") or "").strip() or None,
            target_kind=derive_target_kind(
                surface=str(event.get("surface") or ""),
                action=str(event.get("action") or ""),
                target=target,
            ),
            target_id=target,
            before_state=None,
            after_state=None,
            receipt=None,
            metadata=mutation_audit_metadata(event),
        )
