from __future__ import annotations

import importlib
import importlib.util
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ConflictProbeResult:
    conflict_detected: bool
    winning_intent_id: str | None = None
    conflicting_intent_id: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: Any) -> "ConflictProbeResult":
        if isinstance(value, cls):
            return value
        if isinstance(value, bool):
            return cls(conflict_detected=value)
        if not isinstance(value, dict):
            raise ValueError("conflict probe must return a boolean, mapping, or ConflictProbeResult")
        conflict_detected = bool(value.get("conflict_detected"))
        winning_intent_id = value.get("winning_intent_id")
        conflicting_intent_id = value.get("conflicting_intent_id")
        message = value.get("message")
        metadata = value.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("conflict probe metadata must be a mapping")
        return cls(
            conflict_detected=conflict_detected,
            winning_intent_id=str(winning_intent_id).strip() or None if winning_intent_id is not None else None,
            conflicting_intent_id=(
                str(conflicting_intent_id).strip() or None if conflicting_intent_id is not None else None
            ),
            message=str(message).strip() or None if message is not None else None,
            metadata=dict(metadata),
        )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "conflict_detected": self.conflict_detected,
            "metadata": dict(self.metadata),
        }
        if self.winning_intent_id:
            payload["winning_intent_id"] = self.winning_intent_id
        if self.conflicting_intent_id:
            payload["conflicting_intent_id"] = self.conflicting_intent_id
        if self.message:
            payload["message"] = self.message
        return payload


@dataclass(frozen=True)
class SpeculativeExecutionRecord:
    actor_intent_id: str
    workflow_id: str
    status: str
    probe_due_at: str
    updated_at: str
    job_id: str | None = None
    conflict_with: str | None = None
    compensating_workflow_id: str | None = None
    compensating_job_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "actor_intent_id": self.actor_intent_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "probe_due_at": self.probe_due_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }
        if self.job_id:
            payload["job_id"] = self.job_id
        if self.conflict_with:
            payload["conflict_with"] = self.conflict_with
        if self.compensating_workflow_id:
            payload["compensating_workflow_id"] = self.compensating_workflow_id
        if self.compensating_job_id:
            payload["compensating_job_id"] = self.compensating_job_id
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpeculativeExecutionRecord":
        metadata = payload.get("metadata", {})
        return cls(
            actor_intent_id=str(payload["actor_intent_id"]),
            workflow_id=str(payload["workflow_id"]),
            status=str(payload["status"]),
            probe_due_at=str(payload["probe_due_at"]),
            updated_at=str(payload["updated_at"]),
            job_id=str(payload["job_id"]) if payload.get("job_id") else None,
            conflict_with=str(payload["conflict_with"]) if payload.get("conflict_with") else None,
            compensating_workflow_id=(
                str(payload["compensating_workflow_id"]) if payload.get("compensating_workflow_id") else None
            ),
            compensating_job_id=str(payload["compensating_job_id"]) if payload.get("compensating_job_id") else None,
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )


class SpeculativeStateStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path(__file__).resolve().parents[2] / ".local" / "scheduler" / "speculative.json")

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"executions": {}}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"executions": {}}
        executions = payload.get("executions")
        if not isinstance(executions, dict):
            payload["executions"] = {}
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def upsert(self, record: SpeculativeExecutionRecord) -> None:
        payload = self._load()
        payload.setdefault("executions", {})[record.actor_intent_id] = record.as_dict()
        self._write(payload)

    def mark_status(
        self,
        actor_intent_id: str,
        *,
        status: str,
        conflict_with: str | None = None,
        compensating_workflow_id: str | None = None,
        compensating_job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = self._load()
        current = payload.setdefault("executions", {}).get(actor_intent_id)
        if not isinstance(current, dict):
            return
        updated = dict(current)
        updated["status"] = status
        updated["updated_at"] = _utc_now()
        if conflict_with is not None:
            updated["conflict_with"] = conflict_with
        if compensating_workflow_id is not None:
            updated["compensating_workflow_id"] = compensating_workflow_id
        if compensating_job_id is not None:
            updated["compensating_job_id"] = compensating_job_id
        if metadata is not None:
            updated["metadata"] = dict(metadata)
        payload["executions"][actor_intent_id] = updated
        self._write(payload)


def _load_probe_callable(repo_root: Path, spec: dict[str, str]) -> Callable[[dict[str, Any]], Any]:
    callable_name = spec["callable"]
    if "path" in spec:
        path = Path(spec["path"])
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        module_name = f"lv3_speculative_probe_{uuid.uuid4().hex}"
        loader = importlib.util.spec_from_file_location(module_name, path)
        if loader is None or loader.loader is None:
            raise ImportError(f"unable to load speculative probe from {path}")
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
    else:
        module = importlib.import_module(spec["module"])
    fn = getattr(module, callable_name, None)
    if not callable(fn):
        raise TypeError(f"speculative conflict probe '{callable_name}' is not callable")
    return fn


def run_conflict_probe(
    *,
    repo_root: Path,
    probe_spec: dict[str, str],
    context: dict[str, Any],
) -> ConflictProbeResult:
    fn = _load_probe_callable(repo_root, probe_spec)
    return ConflictProbeResult.from_value(fn(context))


def build_compensating_arguments(
    *,
    original_arguments: dict[str, Any],
    original_workflow_id: str,
    actor_intent_id: str,
    job_id: str | None,
    conflict: ConflictProbeResult,
) -> dict[str, Any]:
    payload = dict(original_arguments)
    payload["parent_actor_intent_id"] = actor_intent_id
    payload["rollback_parent_intent_id"] = actor_intent_id
    payload["speculative_rollback_of"] = actor_intent_id
    payload["speculative_original_workflow_id"] = original_workflow_id
    if job_id:
        payload["speculative_original_job_id"] = job_id
    if conflict.conflicting_intent_id:
        payload["speculative_conflict_with"] = conflict.conflicting_intent_id
    payload["speculative_conflict"] = conflict.as_dict()
    return payload
