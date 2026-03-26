from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from platform.concurrency import default_state_path, isoformat, locked_json_state, parse_timestamp, utc_now
from platform.conflict import infer_resource_claims


SCHEDULER_INTENT_QUEUE_STATE_ENV = "LV3_SCHEDULER_INTENT_QUEUE_PATH"
SCHEDULER_INTENT_QUEUE_STATE_SUBPATH = Path("lv3-concurrency") / "scheduler-intent-queue.json"


def _queue_priority_for(
    *,
    workflow_id: str,
    requested_by: str,
    autonomous: bool,
    repo_root: Path,
    explicit: int | None,
) -> int:
    if explicit is not None:
        return explicit
    tags: list[str] = []
    try:
        payload = json.loads((repo_root / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
        workflow = payload.get("workflows", {}).get(workflow_id, {})
        raw_tags = workflow.get("tags", [])
        if isinstance(raw_tags, list):
            tags = [str(item).strip().lower() for item in raw_tags if isinstance(item, str) and str(item).strip()]
    except (OSError, json.JSONDecodeError, AttributeError):
        tags = []
    actor = requested_by.strip().lower()
    if "incident-response" in tags or "incident" in tags:
        return 5
    if actor.startswith("operator:") or actor.startswith("operator/"):
        return 20
    if actor.startswith("agent/triage"):
        return 40
    if "drift" in tags or actor.startswith("agent/observation"):
        return 60
    if "maintenance" in tags or "scheduled" in tags:
        return 90
    if autonomous:
        return 60
    return 50


@dataclass(frozen=True)
class SchedulerQueuedIntent:
    queue_id: str
    actor_intent_id: str
    workflow_id: str
    requested_by: str
    autonomous: bool
    arguments: dict[str, Any]
    target_service_id: str | None
    target_vm: str | None
    risk_class: str | None
    required_read_surfaces: list[str]
    resource_claims: list[dict[str, Any]]
    required_resources: list[str]
    priority: int
    queued_at: str
    expires_at: str
    attempts: int
    last_conflict: str | None
    status: str
    notify_channel: str | None = None
    completion_status: str | None = None
    completion_metadata: dict[str, Any] | None = None
    dispatched_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "actor_intent_id": self.actor_intent_id,
            "workflow_id": self.workflow_id,
            "requested_by": self.requested_by,
            "autonomous": self.autonomous,
            "arguments": self.arguments,
            "target_service_id": self.target_service_id,
            "target_vm": self.target_vm,
            "risk_class": self.risk_class,
            "required_read_surfaces": list(self.required_read_surfaces),
            "resource_claims": list(self.resource_claims),
            "required_resources": list(self.required_resources),
            "priority": self.priority,
            "queued_at": self.queued_at,
            "expires_at": self.expires_at,
            "attempts": self.attempts,
            "last_conflict": self.last_conflict,
            "status": self.status,
            "notify_channel": self.notify_channel,
            "completion_status": self.completion_status,
            "completion_metadata": self.completion_metadata or {},
            "dispatched_at": self.dispatched_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SchedulerQueuedIntent:
        return cls(
            queue_id=str(payload["queue_id"]),
            actor_intent_id=str(payload["actor_intent_id"]),
            workflow_id=str(payload["workflow_id"]),
            requested_by=str(payload["requested_by"]),
            autonomous=bool(payload.get("autonomous", False)),
            arguments=dict(payload.get("arguments", {})) if isinstance(payload.get("arguments"), dict) else {},
            target_service_id=str(payload["target_service_id"]).strip() if payload.get("target_service_id") else None,
            target_vm=str(payload["target_vm"]).strip() if payload.get("target_vm") else None,
            risk_class=str(payload["risk_class"]).strip() if payload.get("risk_class") else None,
            required_read_surfaces=[
                str(item).strip()
                for item in payload.get("required_read_surfaces", [])
                if isinstance(item, str) and str(item).strip()
            ],
            resource_claims=[dict(item) for item in payload.get("resource_claims", []) if isinstance(item, dict)],
            required_resources=[
                str(item).strip()
                for item in payload.get("required_resources", [])
                if isinstance(item, str) and str(item).strip()
            ],
            priority=int(payload.get("priority", 50)),
            queued_at=str(payload["queued_at"]),
            expires_at=str(payload["expires_at"]),
            attempts=int(payload.get("attempts", 0)),
            last_conflict=str(payload["last_conflict"]).strip() if payload.get("last_conflict") else None,
            status=str(payload.get("status", "waiting")),
            notify_channel=str(payload["notify_channel"]).strip() if payload.get("notify_channel") else None,
            completion_status=str(payload["completion_status"]).strip() if payload.get("completion_status") else None,
            completion_metadata=dict(payload.get("completion_metadata", {}))
            if isinstance(payload.get("completion_metadata"), dict)
            else {},
            dispatched_at=str(payload["dispatched_at"]).strip() if payload.get("dispatched_at") else None,
        )

    def as_scheduler_intent(self) -> SimpleNamespace:
        return SimpleNamespace(
            id=self.actor_intent_id,
            intent_id=self.actor_intent_id,
            actor_intent_id=self.actor_intent_id,
            workflow_id=self.workflow_id,
            arguments=dict(self.arguments),
            target_service_id=self.target_service_id,
            target_vm=self.target_vm,
            resource_claims=list(self.resource_claims),
            required_read_surfaces=list(self.required_read_surfaces),
            risk_class=self.risk_class,
            queue_if_conflicted=False,
        )


class SchedulerIntentQueueStore:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        state_path: Path | None = None,
        now_fn: Any | None = None,
    ) -> None:
        self._repo_root = repo_root or Path(__file__).resolve().parents[2]
        self._state_path = state_path or default_state_path(
            env_var=SCHEDULER_INTENT_QUEUE_STATE_ENV,
            repo_root=self._repo_root,
            state_subpath=SCHEDULER_INTENT_QUEUE_STATE_SUBPATH,
        )
        self._now = now_fn or utc_now

    def enqueue(
        self,
        intent: Any,
        *,
        requested_by: str,
        autonomous: bool,
        expires_in_seconds: int,
        priority: int | None = None,
        last_conflict: str | None = None,
        notify_channel: str | None = None,
    ) -> SchedulerQueuedIntent:
        queued = self._build_entry(
            intent,
            requested_by=requested_by,
            autonomous=autonomous,
            expires_in_seconds=expires_in_seconds,
            priority=priority,
            last_conflict=last_conflict,
            notify_channel=notify_channel,
        )
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            items = [SchedulerQueuedIntent.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
            self._purge_expired_in_memory(items)
            for item in items:
                if item.actor_intent_id == queued.actor_intent_id and item.status in {"waiting", "dispatching"}:
                    state["items"] = [entry.as_dict() for entry in items]
                    return item
            items.append(queued)
            state["items"] = [entry.as_dict() for entry in items]
            return queued

    def claim_ready(
        self,
        *,
        resource_hints: list[str] | None = None,
        workflow_hints: list[str] | None = None,
        limit: int = 1,
    ) -> list[SchedulerQueuedIntent]:
        claimed: list[SchedulerQueuedIntent] = []
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            items = [SchedulerQueuedIntent.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
            self._purge_expired_in_memory(items)
            for item in self._sorted_waiting(items):
                if not self._matches_hints(item, resource_hints=resource_hints, workflow_hints=workflow_hints):
                    continue
                updated = SchedulerQueuedIntent(
                    **{
                        **item.as_dict(),
                        "status": "dispatching",
                        "attempts": item.attempts + 1,
                    }
                )
                for index, candidate in enumerate(items):
                    if candidate.queue_id == item.queue_id:
                        items[index] = updated
                        break
                claimed.append(updated)
                if len(claimed) >= max(limit, 1):
                    break
            state["items"] = [entry.as_dict() for entry in items]
        return claimed

    def requeue(self, queue_id: str, *, reason: str | None = None) -> None:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            items = [SchedulerQueuedIntent.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
            for index, item in enumerate(items):
                if item.queue_id != queue_id:
                    continue
                items[index] = SchedulerQueuedIntent(
                    **{
                        **item.as_dict(),
                        "status": "waiting",
                        "last_conflict": reason,
                    }
                )
                break
            state["items"] = [entry.as_dict() for entry in items]

    def mark_dispatched(self, queue_id: str, *, completion_status: str, metadata: dict[str, Any] | None = None) -> None:
        self._mark_terminal(queue_id, status="dispatched", completion_status=completion_status, metadata=metadata)

    def mark_expired(self, queue_id: str, *, reason: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._mark_terminal(queue_id, status="expired", completion_status=reason or "expired", metadata=metadata)

    def expire_waiting(self) -> list[SchedulerQueuedIntent]:
        expired: list[SchedulerQueuedIntent] = []
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            items = [SchedulerQueuedIntent.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
            now = self._now()
            updated_items: list[SchedulerQueuedIntent] = []
            for item in items:
                if item.status == "waiting" and parse_timestamp(item.expires_at) <= now:
                    expired_item = SchedulerQueuedIntent(
                        **{
                            **item.as_dict(),
                            "status": "expired",
                            "completion_status": "expired",
                            "last_conflict": item.last_conflict or "queue TTL exceeded",
                            "completion_metadata": {"expired_at": isoformat(now)},
                        }
                    )
                    expired.append(expired_item)
                    updated_items.append(expired_item)
                else:
                    updated_items.append(item)
            state["items"] = [entry.as_dict() for entry in updated_items]
        return expired

    def stats(self) -> dict[str, Any]:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            items = [SchedulerQueuedIntent.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
            self._purge_expired_in_memory(items)
            waiting = self._sorted_waiting(items)
            now = self._now()
            oldest_wait_seconds = 0
            if waiting:
                oldest_wait_seconds = max(0, int((now - parse_timestamp(waiting[0].queued_at)).total_seconds()))
            return {
                "depth": len(waiting),
                "high_priority_depth": sum(1 for item in waiting if item.priority <= 20),
                "oldest_wait_seconds": oldest_wait_seconds,
                "waiting": [item.as_dict() for item in waiting[:10]],
            }

    def position_for(self, queue_id: str) -> int | None:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            items = [SchedulerQueuedIntent.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
            waiting = self._sorted_waiting(items)
            for index, item in enumerate(waiting, start=1):
                if item.queue_id == queue_id:
                    return index
        return None

    def _build_entry(
        self,
        intent: Any,
        *,
        requested_by: str,
        autonomous: bool,
        expires_in_seconds: int,
        priority: int | None,
        last_conflict: str | None,
        notify_channel: str | None,
    ) -> SchedulerQueuedIntent:
        actor_intent_id = None
        for field in ("actor_intent_id", "intent_id", "id"):
            value = getattr(intent, field, None)
            if isinstance(value, str) and value.strip():
                actor_intent_id = value.strip()
                break
        if actor_intent_id is None:
            actor_intent_id = str(uuid.uuid4())
        workflow_id = str(getattr(intent, "workflow_id", "")).strip()
        arguments = getattr(intent, "arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        target_service_id = getattr(intent, "target_service_id", None)
        target_vm = getattr(intent, "target_vm", None)
        resource_claims = getattr(intent, "resource_claims", None)
        if not isinstance(resource_claims, list) or not resource_claims:
            payload = {
                "workflow_id": workflow_id,
                "arguments": arguments,
                "target_service_id": target_service_id,
                "target_vm": target_vm,
            }
            resource_claims = [claim.as_dict() for claim in infer_resource_claims(payload, repo_root=self._repo_root)]
        required_resources = [
            str(item.get("resource", "")).strip()
            for item in resource_claims
            if isinstance(item, dict) and str(item.get("resource", "")).strip()
        ]
        queue_priority = _queue_priority_for(
            workflow_id=workflow_id,
            requested_by=requested_by,
            autonomous=autonomous,
            repo_root=self._repo_root,
            explicit=priority,
        )
        now = self._now()
        required_read_surfaces = getattr(intent, "required_read_surfaces", [])
        if not isinstance(required_read_surfaces, list):
            required_read_surfaces = []
        risk_class = getattr(intent, "final_risk_class", None) or getattr(intent, "risk_class", None)
        return SchedulerQueuedIntent(
            queue_id=str(uuid.uuid4()),
            actor_intent_id=actor_intent_id,
            workflow_id=workflow_id,
            requested_by=requested_by,
            autonomous=autonomous,
            arguments=dict(arguments),
            target_service_id=str(target_service_id).strip() if isinstance(target_service_id, str) and target_service_id.strip() else None,
            target_vm=str(target_vm).strip() if isinstance(target_vm, str) and target_vm.strip() else None,
            risk_class=str(risk_class).strip() if risk_class else None,
            required_read_surfaces=[
                str(item).strip()
                for item in required_read_surfaces
                if isinstance(item, str) and str(item).strip()
            ],
            resource_claims=list(resource_claims),
            required_resources=required_resources,
            priority=queue_priority,
            queued_at=isoformat(now),
            expires_at=isoformat(now + timedelta(seconds=max(expires_in_seconds, 1))),
            attempts=0,
            last_conflict=last_conflict,
            status="waiting",
            notify_channel=notify_channel,
            completion_status=None,
            completion_metadata={},
            dispatched_at=None,
        )

    def _mark_terminal(
        self,
        queue_id: str,
        *,
        status: str,
        completion_status: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            items = [SchedulerQueuedIntent.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
            now = isoformat(self._now())
            for index, item in enumerate(items):
                if item.queue_id != queue_id:
                    continue
                items[index] = SchedulerQueuedIntent(
                    **{
                        **item.as_dict(),
                        "status": status,
                        "completion_status": completion_status,
                        "completion_metadata": metadata or {},
                        "dispatched_at": now if status == "dispatched" else item.dispatched_at,
                        "last_conflict": item.last_conflict if status == "dispatched" else completion_status,
                    }
                )
                break
            state["items"] = [entry.as_dict() for entry in items]

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"schema_version": "1.0.0", "items": []}

    @staticmethod
    def _sorted_waiting(items: list[SchedulerQueuedIntent]) -> list[SchedulerQueuedIntent]:
        waiting = [item for item in items if item.status == "waiting"]
        return sorted(waiting, key=lambda item: (item.priority, item.queued_at, item.queue_id))

    @staticmethod
    def _matches_hints(
        item: SchedulerQueuedIntent,
        *,
        resource_hints: list[str] | None,
        workflow_hints: list[str] | None,
    ) -> bool:
        hints = [hint for hint in (resource_hints or []) if hint]
        workflows = [hint for hint in (workflow_hints or []) if hint]
        if not hints and not workflows:
            return True
        if workflows and item.workflow_id in workflows:
            return True
        if hints and any(resource in hints for resource in item.required_resources):
            return True
        return False

    def _purge_expired_in_memory(self, items: list[SchedulerQueuedIntent]) -> None:
        now = self._now()
        for index, item in enumerate(list(items)):
            if item.status != "waiting":
                continue
            if parse_timestamp(item.expires_at) > now:
                continue
            items[index] = SchedulerQueuedIntent(
                **{
                    **item.as_dict(),
                    "status": "expired",
                    "completion_status": "expired",
                    "last_conflict": item.last_conflict or "queue TTL exceeded",
                    "completion_metadata": {"expired_at": isoformat(now)},
                }
            )
