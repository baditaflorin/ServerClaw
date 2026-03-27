from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from platform.concurrency import default_state_path, isoformat, locked_json_state, parse_timestamp, utc_now


COORDINATION_STATE_ENV = "LV3_COORDINATION_MAP_PATH"
COORDINATION_STATE_SUBPATH = Path("lv3-concurrency") / "coordination-map.json"


@dataclass(frozen=True)
class AgentSessionEntry:
    context_id: str
    agent_id: str
    session_label: str
    current_phase: str = "idle"
    current_intent_id: str | None = None
    current_workflow_id: str | None = None
    current_target: str | None = None
    held_locks: list[str] = field(default_factory=list)
    held_lanes: list[str] = field(default_factory=list)
    reserved_budget: dict[str, Any] = field(default_factory=dict)
    batch_id: str | None = None
    batch_stage: int = 0
    step_index: int = 0
    step_count: int = 0
    progress_pct: float = 0.0
    last_heartbeat: str = field(default_factory=lambda: isoformat(utc_now()))
    status: str = "active"
    blocked_reason: str | None = None
    error_count: int = 0
    started_at: str = field(default_factory=lambda: isoformat(utc_now()))
    estimated_completion: str | None = None
    expires_at: str = field(default_factory=lambda: isoformat(utc_now()))

    def __post_init__(self) -> None:
        if not self.context_id.strip():
            raise ValueError("context_id must be a non-empty string")
        if not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        if not self.session_label.strip():
            raise ValueError("session_label must be a non-empty string")
        if not 0.0 <= float(self.progress_pct) <= 1.0:
            raise ValueError("progress_pct must be between 0.0 and 1.0")

    def as_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "agent_id": self.agent_id,
            "session_label": self.session_label,
            "current_phase": self.current_phase,
            "current_intent_id": self.current_intent_id,
            "current_workflow_id": self.current_workflow_id,
            "current_target": self.current_target,
            "held_locks": list(self.held_locks),
            "held_lanes": list(self.held_lanes),
            "reserved_budget": dict(self.reserved_budget),
            "batch_id": self.batch_id,
            "batch_stage": self.batch_stage,
            "step_index": self.step_index,
            "step_count": self.step_count,
            "progress_pct": self.progress_pct,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "error_count": self.error_count,
            "started_at": self.started_at,
            "estimated_completion": self.estimated_completion,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AgentSessionEntry:
        return cls(
            context_id=str(payload.get("context_id", "")).strip(),
            agent_id=str(payload.get("agent_id", "")).strip(),
            session_label=str(payload.get("session_label", "")).strip(),
            current_phase=str(payload.get("current_phase", "idle")).strip() or "idle",
            current_intent_id=_optional_str(payload.get("current_intent_id")),
            current_workflow_id=_optional_str(payload.get("current_workflow_id")),
            current_target=_optional_str(payload.get("current_target")),
            held_locks=[str(item) for item in payload.get("held_locks", []) if str(item).strip()],
            held_lanes=[str(item) for item in payload.get("held_lanes", []) if str(item).strip()],
            reserved_budget=dict(payload.get("reserved_budget", {}) or {}),
            batch_id=_optional_str(payload.get("batch_id")),
            batch_stage=int(payload.get("batch_stage", 0)),
            step_index=int(payload.get("step_index", 0)),
            step_count=int(payload.get("step_count", 0)),
            progress_pct=float(payload.get("progress_pct", 0.0)),
            last_heartbeat=str(payload.get("last_heartbeat") or isoformat(utc_now())),
            status=str(payload.get("status", "active")).strip() or "active",
            blocked_reason=_optional_str(payload.get("blocked_reason")),
            error_count=int(payload.get("error_count", 0)),
            started_at=str(payload.get("started_at") or isoformat(utc_now())),
            estimated_completion=_optional_str(payload.get("estimated_completion")),
            expires_at=str(payload.get("expires_at") or isoformat(utc_now())),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


class AgentCoordinationMap:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        state_path: Path | None = None,
        ttl_seconds: int = 300,
        now_fn: Any | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._repo_root = repo_root
        self._state_path = state_path or default_state_path(
            env_var=COORDINATION_STATE_ENV,
            repo_root=repo_root,
            state_subpath=COORDINATION_STATE_SUBPATH,
        )
        self._ttl_seconds = ttl_seconds
        self._now = now_fn or utc_now

    def publish(self, entry: AgentSessionEntry) -> AgentSessionEntry:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            self._purge_locked(state)
            payload = entry.as_dict()
            payload["last_heartbeat"] = isoformat(self._now())
            payload["expires_at"] = isoformat(self._now() + timedelta(seconds=self._ttl_seconds))
            state["sessions"][entry.context_id] = payload
            return AgentSessionEntry.from_dict(payload)

    def read(self, context_id: str) -> AgentSessionEntry | None:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            self._purge_locked(state)
            payload = state["sessions"].get(context_id)
            return AgentSessionEntry.from_dict(payload) if isinstance(payload, dict) else None

    def read_all(self) -> list[AgentSessionEntry]:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            self._purge_locked(state)
            entries = [
                AgentSessionEntry.from_dict(payload)
                for payload in state["sessions"].values()
                if isinstance(payload, dict)
            ]
        return sorted(entries, key=lambda entry: (entry.agent_id, entry.context_id))

    def read_by_target(self, target: str) -> list[AgentSessionEntry]:
        return [entry for entry in self.read_all() if entry.current_target == target]

    def delete(self, context_id: str) -> bool:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            self._purge_locked(state)
            return state["sessions"].pop(context_id, None) is not None

    def _purge_locked(self, state: dict[str, Any]) -> None:
        now = self._now()
        sessions = state.setdefault("sessions", {})
        expired = []
        for context_id, payload in sessions.items():
            if not isinstance(payload, dict):
                expired.append(context_id)
                continue
            expires_at = payload.get("expires_at")
            if expires_at and parse_timestamp(str(expires_at)) <= now:
                expired.append(context_id)
                continue
            heartbeat = payload.get("last_heartbeat")
            if heartbeat and (now - parse_timestamp(str(heartbeat))).total_seconds() > self._ttl_seconds:
                expired.append(context_id)
        for context_id in expired:
            sessions.pop(context_id, None)

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"schema_version": "1.0.0", "sessions": {}}
