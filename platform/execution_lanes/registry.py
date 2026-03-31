from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from platform.datetime_compat import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .catalog import REPO_ROOT, LaneResolution, resolve_lanes


DEFAULT_STATE_SUBPATH = Path("lv3-execution-lanes") / "registry.json"


def _git_common_dir(repo_root: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def _default_state_path(repo_root: Path) -> Path:
    override = os.environ.get("LV3_EXECUTION_LANE_STATE_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    common_dir = _git_common_dir(repo_root)
    if common_dir is not None:
        return common_dir / DEFAULT_STATE_SUBPATH
    return repo_root / ".local" / "state" / "execution-lanes" / "registry.json"


def _intent_payload(intent: Any) -> dict[str, Any]:
    if hasattr(intent, "as_dict"):
        payload = intent.as_dict()
        if isinstance(payload, dict):
            return payload
    if isinstance(intent, dict):
        return dict(intent)
    payload: dict[str, Any] = {}
    for field in (
        "id",
        "intent_id",
        "workflow_id",
        "arguments",
        "target_service_id",
        "target_vm",
        "required_read_surfaces",
        "risk_class",
        "final_risk_class",
        "required_lanes",
    ):
        if hasattr(intent, field):
            payload[field] = getattr(intent, field)
    return payload


@dataclass(frozen=True)
class LaneLease:
    actor_intent_id: str
    primary_lane_id: str
    required_lanes: tuple[str, ...]
    leased_at: str
    expires_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "actor_intent_id": self.actor_intent_id,
            "primary_lane_id": self.primary_lane_id,
            "required_lanes": list(self.required_lanes),
            "leased_at": self.leased_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LaneLease:
        return cls(
            actor_intent_id=str(payload["actor_intent_id"]),
            primary_lane_id=str(payload["primary_lane_id"]),
            required_lanes=tuple(
                str(item) for item in payload.get("required_lanes", []) if isinstance(item, str) and str(item).strip()
            ),
            leased_at=str(payload["leased_at"]),
            expires_at=str(payload["expires_at"]),
        )


@dataclass(frozen=True)
class LaneQueueEntry:
    queue_id: str
    actor_intent_id: str
    requested_by: str
    autonomous: bool
    primary_lane_id: str
    required_lanes: tuple[str, ...]
    queued_at: str
    expires_at: str
    ttl_seconds: int
    intent_payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "actor_intent_id": self.actor_intent_id,
            "requested_by": self.requested_by,
            "autonomous": self.autonomous,
            "primary_lane_id": self.primary_lane_id,
            "required_lanes": list(self.required_lanes),
            "queued_at": self.queued_at,
            "expires_at": self.expires_at,
            "ttl_seconds": self.ttl_seconds,
            "intent_payload": self.intent_payload,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LaneQueueEntry:
        return cls(
            queue_id=str(payload["queue_id"]),
            actor_intent_id=str(payload["actor_intent_id"]),
            requested_by=str(payload.get("requested_by", "operator:unknown")),
            autonomous=bool(payload.get("autonomous", False)),
            primary_lane_id=str(payload["primary_lane_id"]),
            required_lanes=tuple(
                str(item) for item in payload.get("required_lanes", []) if isinstance(item, str) and str(item).strip()
            ),
            queued_at=str(payload["queued_at"]),
            expires_at=str(payload["expires_at"]),
            ttl_seconds=int(payload.get("ttl_seconds", 0)),
            intent_payload=dict(payload.get("intent_payload", {})),
        )


@dataclass(frozen=True)
class LaneReservationResult:
    status: str
    resolution: LaneResolution
    lease: LaneLease | None = None
    queue_entry: LaneQueueEntry | None = None
    active_count: int = 0
    max_concurrent_ops: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "primary_lane_id": self.resolution.primary_lane_id,
            "required_lanes": list(self.resolution.required_lanes),
            "dependency_lanes": list(self.resolution.dependency_lanes),
            "active_count": self.active_count,
            "max_concurrent_ops": self.max_concurrent_ops,
        }
        if self.lease is not None:
            payload["lease"] = self.lease.as_dict()
        if self.queue_entry is not None:
            payload["queue_entry"] = self.queue_entry.as_dict()
        return payload


class LaneRegistry:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        state_path: Path | None = None,
        now_fn: Any | None = None,
    ) -> None:
        self._repo_root = repo_root or REPO_ROOT
        self._state_path = state_path or _default_state_path(self._repo_root)
        self._lock_path = self._state_path.with_suffix(".lock")
        self._now = now_fn or (lambda: datetime.now(UTC))

    def reserve(self, intent: Any, *, actor_intent_id: str, ttl_seconds: int) -> LaneReservationResult:
        resolution = resolve_lanes(intent, repo_root=self._repo_root)
        if resolution.primary_lane_id is None:
            return LaneReservationResult(status="not_applicable", resolution=resolution)

        now = self._now()
        expires_at = now + timedelta(seconds=ttl_seconds)

        from .catalog import load_execution_lane_catalog

        catalog = load_execution_lane_catalog(repo_root=self._repo_root)
        lane = catalog.lanes[resolution.primary_lane_id]
        with self._locked_state() as state:
            self._purge(state)
            active = state.setdefault("active", {}).setdefault(resolution.primary_lane_id, [])
            active_count = len(active)
            if active_count >= lane.max_concurrent_ops:
                return LaneReservationResult(
                    status="busy",
                    resolution=resolution,
                    active_count=active_count,
                    max_concurrent_ops=lane.max_concurrent_ops,
                )
            lease = LaneLease(
                actor_intent_id=actor_intent_id,
                primary_lane_id=resolution.primary_lane_id,
                required_lanes=resolution.required_lanes,
                leased_at=self._timestamp(now),
                expires_at=self._timestamp(expires_at),
            )
            active.append(lease.as_dict())
            return LaneReservationResult(
                status="acquired",
                resolution=resolution,
                lease=lease,
                active_count=len(active),
                max_concurrent_ops=lane.max_concurrent_ops,
            )

    def enqueue(
        self,
        intent: Any,
        *,
        actor_intent_id: str,
        requested_by: str,
        ttl_seconds: int,
        autonomous: bool,
    ) -> LaneQueueEntry | None:
        resolution = resolve_lanes(intent, repo_root=self._repo_root)
        if resolution.primary_lane_id is None:
            return None
        payload = _intent_payload(intent)
        now = self._now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        queue_id = f"{resolution.primary_lane_id}:{actor_intent_id}"
        entry = LaneQueueEntry(
            queue_id=queue_id,
            actor_intent_id=actor_intent_id,
            requested_by=requested_by,
            autonomous=autonomous,
            primary_lane_id=resolution.primary_lane_id,
            required_lanes=resolution.required_lanes,
            queued_at=self._timestamp(now),
            expires_at=self._timestamp(expires_at),
            ttl_seconds=ttl_seconds,
            intent_payload=payload,
        )
        with self._locked_state() as state:
            self._purge(state)
            queue = state.setdefault("queue", [])
            for raw in queue:
                if not isinstance(raw, dict):
                    continue
                if str(raw.get("queue_id")) == queue_id:
                    return LaneQueueEntry.from_dict(raw)
            queue.append(entry.as_dict())
        return entry

    def lease_dispatchable(self, *, max_items: int | None = None) -> list[LaneQueueEntry]:
        from .catalog import load_execution_lane_catalog

        catalog = load_execution_lane_catalog(repo_root=self._repo_root)
        if not catalog.lanes:
            return []
        with self._locked_state() as state:
            self._purge(state)
            queue = [LaneQueueEntry.from_dict(item) for item in state.get("queue", []) if isinstance(item, dict)]
            if not queue:
                return []
            active = state.setdefault("active", {})
            remaining: list[dict[str, Any]] = []
            dispatchable: list[LaneQueueEntry] = []
            for entry in queue:
                lane = catalog.lanes.get(entry.primary_lane_id)
                lane_active = active.setdefault(entry.primary_lane_id, [])
                if (
                    lane is not None
                    and len(lane_active) < lane.max_concurrent_ops
                    and (max_items is None or len(dispatchable) < max_items)
                ):
                    lease = LaneLease(
                        actor_intent_id=entry.actor_intent_id,
                        primary_lane_id=entry.primary_lane_id,
                        required_lanes=entry.required_lanes,
                        leased_at=self._timestamp(self._now()),
                        expires_at=self._timestamp(self._now() + timedelta(seconds=entry.ttl_seconds)),
                    )
                    lane_active.append(lease.as_dict())
                    dispatchable.append(entry)
                    continue
                remaining.append(entry.as_dict())
            state["queue"] = remaining
        return dispatchable

    def release(self, actor_intent_id: str) -> None:
        with self._locked_state() as state:
            self._purge(state)
            active = state.setdefault("active", {})
            for lane_id, entries in list(active.items()):
                if not isinstance(entries, list):
                    continue
                active[lane_id] = [
                    entry
                    for entry in entries
                    if not isinstance(entry, dict) or str(entry.get("actor_intent_id")) != actor_intent_id
                ]
            queue = state.setdefault("queue", [])
            state["queue"] = [
                entry
                for entry in queue
                if not isinstance(entry, dict) or str(entry.get("actor_intent_id")) != actor_intent_id
            ]

    def snapshot(self) -> dict[str, Any]:
        with self._locked_state() as state:
            self._purge(state)
            active = {
                lane_id: [LaneLease.from_dict(entry).as_dict() for entry in entries if isinstance(entry, dict)]
                for lane_id, entries in state.get("active", {}).items()
                if isinstance(entries, list)
            }
            queue = [LaneQueueEntry.from_dict(entry).as_dict() for entry in state.get("queue", []) if isinstance(entry, dict)]
            return {
                "schema_version": state.get("schema_version", "1.0.0"),
                "active": active,
                "queue": queue,
            }

    def _purge(self, state: dict[str, Any]) -> None:
        now = self._now()
        active = state.setdefault("active", {})
        for lane_id, entries in list(active.items()):
            if not isinstance(entries, list):
                active[lane_id] = []
                continue
            active[lane_id] = [
                entry
                for entry in entries
                if isinstance(entry, dict) and self._parse_timestamp(str(entry.get("expires_at", ""))) > now
            ]
        queue = state.setdefault("queue", [])
        state["queue"] = [
            entry
            for entry in queue
            if isinstance(entry, dict) and self._parse_timestamp(str(entry.get("expires_at", ""))) > now
        ]

    @contextmanager
    def _locked_state(self) -> Iterator[dict[str, Any]]:
        import fcntl

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                if self._state_path.exists():
                    raw = self._state_path.read_text(encoding="utf-8").strip()
                    state = json.loads(raw) if raw else self._empty_state()
                else:
                    state = self._empty_state()
                yield state
                self._state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"schema_version": "1.0.0", "active": {}, "queue": []}

    @staticmethod
    def _timestamp(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
