from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from platform.concurrency import default_state_path, isoformat, locked_json_state, parse_timestamp, utc_now


INTENT_QUEUE_STATE_ENV = "LV3_INTENT_QUEUE_PATH"
INTENT_QUEUE_STATE_SUBPATH = Path("lv3-concurrency") / "intent-queue.json"


@dataclass(frozen=True)
class QueuedIntent:
    intent_id: str
    context_id: str
    agent_id: str
    workflow_id: str | None = None
    priority: int = 50
    required_locks: list[str] = field(default_factory=list)
    status: str = "waiting"
    attempts: int = 1
    queued_at: str = field(default_factory=lambda: isoformat(utc_now()))
    not_before: str = field(default_factory=lambda: isoformat(utc_now()))
    reason: str | None = None
    last_updated: str = field(default_factory=lambda: isoformat(utc_now()))

    def __post_init__(self) -> None:
        if not self.intent_id.strip():
            raise ValueError("intent_id must be a non-empty string")
        if not self.context_id.strip():
            raise ValueError("context_id must be a non-empty string")
        if not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "context_id": self.context_id,
            "agent_id": self.agent_id,
            "workflow_id": self.workflow_id,
            "priority": self.priority,
            "required_locks": list(self.required_locks),
            "status": self.status,
            "attempts": self.attempts,
            "queued_at": self.queued_at,
            "not_before": self.not_before,
            "reason": self.reason,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> QueuedIntent:
        return cls(
            intent_id=str(payload.get("intent_id", "")).strip(),
            context_id=str(payload.get("context_id", "")).strip(),
            agent_id=str(payload.get("agent_id", "")).strip(),
            workflow_id=_optional_str(payload.get("workflow_id")),
            priority=int(payload.get("priority", 50)),
            required_locks=[str(item) for item in payload.get("required_locks", []) if str(item).strip()],
            status=str(payload.get("status", "waiting")).strip() or "waiting",
            attempts=int(payload.get("attempts", 1)),
            queued_at=str(payload.get("queued_at") or isoformat(utc_now())),
            not_before=str(payload.get("not_before") or isoformat(utc_now())),
            reason=_optional_str(payload.get("reason")),
            last_updated=str(payload.get("last_updated") or isoformat(utc_now())),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


class IntentQueue:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        state_path: Path | None = None,
        now_fn: Any | None = None,
    ) -> None:
        self._state_path = state_path or default_state_path(
            env_var=INTENT_QUEUE_STATE_ENV,
            repo_root=repo_root,
            state_subpath=INTENT_QUEUE_STATE_SUBPATH,
        )
        self._now = now_fn or utc_now

    def enqueue(
        self,
        *,
        intent_id: str,
        context_id: str,
        agent_id: str,
        workflow_id: str | None = None,
        priority: int = 50,
        required_locks: list[str] | None = None,
        delay_seconds: int = 0,
        reason: str | None = None,
        attempts: int = 1,
    ) -> QueuedIntent:
        now = self._now()
        entry = QueuedIntent(
            intent_id=intent_id,
            context_id=context_id,
            agent_id=agent_id,
            workflow_id=workflow_id,
            priority=priority,
            required_locks=list(required_locks or []),
            status="waiting",
            attempts=attempts,
            queued_at=isoformat(now),
            not_before=isoformat(now + timedelta(seconds=max(delay_seconds, 0))),
            reason=reason,
            last_updated=isoformat(now),
        )
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            state["entries"][intent_id] = entry.as_dict()
        return entry

    def get(self, intent_id: str) -> QueuedIntent | None:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            payload = state["entries"].get(intent_id)
            return QueuedIntent.from_dict(payload) if isinstance(payload, dict) else None

    def read_all(self) -> list[QueuedIntent]:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            entries = [QueuedIntent.from_dict(payload) for payload in state["entries"].values() if isinstance(payload, dict)]
        return sorted(entries, key=lambda entry: (entry.priority, entry.queued_at, entry.intent_id))

    def read_waiting(self) -> list[QueuedIntent]:
        now = self._now()
        return [
            entry
            for entry in self.read_all()
            if entry.status == "waiting" and parse_timestamp(entry.not_before) <= now
        ]

    def mark_running(self, intent_id: str) -> QueuedIntent | None:
        return self._update_status(intent_id, status="running")

    def mark_completed(self, intent_id: str) -> QueuedIntent | None:
        return self._update_status(intent_id, status="completed")

    def requeue(self, intent_id: str, *, delay_seconds: int = 60, reason: str | None = None) -> QueuedIntent | None:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            payload = state["entries"].get(intent_id)
            if not isinstance(payload, dict):
                return None
            entry = QueuedIntent.from_dict(payload)
            updated = QueuedIntent(
                intent_id=entry.intent_id,
                context_id=entry.context_id,
                agent_id=entry.agent_id,
                workflow_id=entry.workflow_id,
                priority=entry.priority,
                required_locks=list(entry.required_locks),
                status="waiting",
                attempts=entry.attempts + 1,
                queued_at=entry.queued_at,
                not_before=isoformat(self._now() + timedelta(seconds=max(delay_seconds, 0))),
                reason=reason or entry.reason,
                last_updated=isoformat(self._now()),
            )
            state["entries"][intent_id] = updated.as_dict()
            return updated

    def delete(self, intent_id: str) -> bool:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            return state["entries"].pop(intent_id, None) is not None

    def _update_status(self, intent_id: str, *, status: str) -> QueuedIntent | None:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            payload = state["entries"].get(intent_id)
            if not isinstance(payload, dict):
                return None
            entry = QueuedIntent.from_dict(payload)
            updated = QueuedIntent(
                intent_id=entry.intent_id,
                context_id=entry.context_id,
                agent_id=entry.agent_id,
                workflow_id=entry.workflow_id,
                priority=entry.priority,
                required_locks=list(entry.required_locks),
                status=status,
                attempts=entry.attempts,
                queued_at=entry.queued_at,
                not_before=entry.not_before,
                reason=entry.reason,
                last_updated=isoformat(self._now()),
            )
            state["entries"][intent_id] = updated.as_dict()
            return updated

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"schema_version": "1.0.0", "entries": {}}
