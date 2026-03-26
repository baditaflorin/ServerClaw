from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from platform.world_state._db import isoformat, parse_timestamp, utc_now


DEFAULT_BUCKET = "agent-coordination"
DEFAULT_TTL_SECONDS = 300
DEFAULT_HEARTBEAT_SECONDS = 30
STATE_FILE_ENV = "LV3_AGENT_COORDINATION_STATE_FILE"


def _default_nats_url() -> str | None:
    value = (
        os.environ.get("LV3_AGENT_COORDINATION_NATS_URL", "").strip()
        or os.environ.get("LV3_NATS_URL", "").strip()
    )
    return value or None


def _default_state_file(repo_root: Path) -> Path:
    override = os.environ.get(STATE_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return repo_root / ".local" / "state" / "agent-coordination" / "sessions.json"


def _default_bucket() -> str:
    return os.environ.get("LV3_AGENT_COORDINATION_BUCKET", "").strip() or DEFAULT_BUCKET


def _default_ttl_seconds() -> int:
    raw = os.environ.get("LV3_AGENT_COORDINATION_TTL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_SECONDS
    return max(30, value)


def _default_heartbeat_seconds() -> int:
    raw = os.environ.get("LV3_AGENT_COORDINATION_HEARTBEAT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_HEARTBEAT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_HEARTBEAT_SECONDS
    return max(5, value)


def _resolve_nats_credentials(repo_root: Path) -> dict[str, str]:
    env_user = os.environ.get("LV3_NATS_USERNAME", "").strip()
    env_password = os.environ.get("LV3_NATS_PASSWORD", "").strip()
    env_password_file = os.environ.get("LV3_NATS_PASSWORD_FILE", "").strip()
    if env_password_file and not env_password:
        password_path = Path(env_password_file).expanduser()
        if password_path.exists():
            env_password = password_path.read_text(encoding="utf-8").strip()
    if env_user and env_password:
        return {"user": env_user, "password": env_password}

    secret_manifest_path = repo_root / "config" / "controller-local-secrets.json"
    if not secret_manifest_path.exists():
        return {}
    try:
        payload = json.loads(secret_manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    secret_entry = payload.get("secrets", {}).get("nats_jetstream_admin_password")
    if not isinstance(secret_entry, dict):
        return {}
    candidate = secret_entry.get("path")
    if not isinstance(candidate, str) or not candidate.strip():
        return {}
    password_path = Path(candidate).expanduser()
    if not password_path.exists():
        return {}
    return {"user": "jetstream-admin", "password": password_path.read_text(encoding="utf-8").strip()}


def _default_event_publisher(subject: str, payload: dict[str, Any]) -> None:
    nats_url = _default_nats_url()
    if not nats_url:
        return
    repo_root = Path(__file__).resolve().parents[2]
    drift_lib_path = repo_root / "scripts" / "drift_lib.py"
    if not drift_lib_path.exists():
        return

    module_name = "lv3_agent_coordination_drift_lib"
    spec = importlib.util.spec_from_file_location(module_name, drift_lib_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(module_name, module)
    spec.loader.exec_module(module)
    module.publish_nats_events(  # pragma: no cover - network side effect
        [{"subject": subject, "payload": payload}],
        nats_url=nats_url,
        credentials=_resolve_nats_credentials(repo_root),
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

    thread = threading.Thread(target=runner, name="agent-coordination-publisher", daemon=True)
    thread.start()


def _sanitize_key_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return normalized.strip("._-") or "session"


def _status_for_phase(phase: str) -> str:
    if phase in {"blocked"}:
        return "blocked"
    if phase in {"escalated"}:
        return "escalated"
    if phase in {"completing", "idle"}:
        return "completing"
    return "active"


@dataclass(frozen=True)
class AgentSessionEntry:
    context_id: str
    agent_id: str
    session_label: str
    current_phase: str
    current_intent_id: str | None = None
    current_workflow_id: str | None = None
    current_target: str | None = None
    held_locks: list[str] = field(default_factory=list)
    held_lanes: list[str] = field(default_factory=list)
    reserved_budget: dict[str, Any] = field(default_factory=dict)
    batch_id: str | None = None
    batch_stage: int | None = None
    step_index: int | None = None
    step_count: int | None = None
    progress_pct: float | None = None
    last_heartbeat: datetime = field(default_factory=utc_now)
    status: str = "active"
    blocked_reason: str | None = None
    error_count: int = 0
    started_at: datetime = field(default_factory=utc_now)
    estimated_completion: datetime | None = None
    expires_at: datetime = field(default_factory=lambda: utc_now() + timedelta(seconds=DEFAULT_TTL_SECONDS))

    def __post_init__(self) -> None:
        if not self.context_id.strip():
            raise ValueError("context_id must be a non-empty string")
        if not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        if not self.session_label.strip():
            raise ValueError("session_label must be a non-empty string")
        if not self.current_phase.strip():
            raise ValueError("current_phase must be a non-empty string")
        if self.step_index is not None and self.step_index < 0:
            raise ValueError("step_index must be >= 0")
        if self.step_count is not None and self.step_count < 0:
            raise ValueError("step_count must be >= 0")
        if self.progress_pct is not None and not 0.0 <= self.progress_pct <= 1.0:
            raise ValueError("progress_pct must be between 0.0 and 1.0")
        if self.error_count < 0:
            raise ValueError("error_count must be >= 0")

    @property
    def key(self) -> str:
        return f"{_sanitize_key_component(self.agent_id)}-{_sanitize_key_component(self.context_id)}"

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
            "last_heartbeat": isoformat(self.last_heartbeat),
            "status": self.status,
            "blocked_reason": self.blocked_reason,
            "error_count": self.error_count,
            "started_at": isoformat(self.started_at),
            "estimated_completion": isoformat(self.estimated_completion) if self.estimated_completion else None,
            "expires_at": isoformat(self.expires_at),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AgentSessionEntry:
        return cls(
            context_id=str(payload.get("context_id", "")).strip(),
            agent_id=str(payload.get("agent_id", "")).strip(),
            session_label=str(payload.get("session_label", "")).strip(),
            current_phase=str(payload.get("current_phase", "")).strip(),
            current_intent_id=_optional_str(payload.get("current_intent_id")),
            current_workflow_id=_optional_str(payload.get("current_workflow_id")),
            current_target=_optional_str(payload.get("current_target")),
            held_locks=_string_list(payload.get("held_locks")),
            held_lanes=_string_list(payload.get("held_lanes")),
            reserved_budget=_mapping(payload.get("reserved_budget")),
            batch_id=_optional_str(payload.get("batch_id")),
            batch_stage=_optional_int(payload.get("batch_stage")),
            step_index=_optional_int(payload.get("step_index")),
            step_count=_optional_int(payload.get("step_count")),
            progress_pct=_optional_float(payload.get("progress_pct")),
            last_heartbeat=parse_timestamp(payload.get("last_heartbeat") or utc_now()),
            status=str(payload.get("status", "active")).strip() or "active",
            blocked_reason=_optional_str(payload.get("blocked_reason")),
            error_count=int(payload.get("error_count", 0)),
            started_at=parse_timestamp(payload.get("started_at") or utc_now()),
            estimated_completion=(
                parse_timestamp(payload["estimated_completion"])
                if isinstance(payload.get("estimated_completion"), str) and payload["estimated_completion"].strip()
                else None
            ),
            expires_at=parse_timestamp(payload.get("expires_at") or utc_now()),
        )


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


class AgentCoordinationStore:
    def __init__(
        self,
        repo_root: Path | str | None = None,
        *,
        nats_url: str | None = None,
        nats_credentials: dict[str, str] | None = None,
        bucket: str | None = None,
        ttl_seconds: int | None = None,
        state_file: Path | str | None = None,
        event_publisher: Callable[[str, dict[str, Any]], None] | None = _default_event_publisher,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
        self.nats_url = nats_url or _default_nats_url()
        self.nats_credentials = nats_credentials or _resolve_nats_credentials(self.repo_root)
        self.bucket = bucket or _default_bucket()
        self.ttl_seconds = ttl_seconds or _default_ttl_seconds()
        self.state_file = Path(state_file) if state_file is not None else _default_state_file(self.repo_root)
        self._event_publisher = event_publisher
        self._now = now

    def publish(self, entry: AgentSessionEntry) -> AgentSessionEntry:
        prepared = self._prepare_entry(entry)
        if self.nats_url:
            try:
                self._run_async(self._publish_nats(prepared))
            except ModuleNotFoundError:
                self._publish_file(prepared)
        else:
            self._publish_file(prepared)
        _publish_async(
            self._event_publisher,
            "platform.agent.state_updated",
            {"entry": prepared.as_dict(), "bucket": self.bucket},
        )
        return prepared

    def delete(self, agent_id: str, context_id: str) -> bool:
        deleted = False
        if self.nats_url:
            try:
                deleted = self._run_async(self._delete_nats(agent_id=agent_id, context_id=context_id))
            except ModuleNotFoundError:
                deleted = self._delete_file(agent_id=agent_id, context_id=context_id)
        else:
            deleted = self._delete_file(agent_id=agent_id, context_id=context_id)
        if deleted:
            _publish_async(
                self._event_publisher,
                "platform.agent.state_updated",
                {"agent_id": agent_id, "context_id": context_id, "deleted": True, "bucket": self.bucket},
            )
        return deleted

    def read_all(self) -> list[AgentSessionEntry]:
        if self.nats_url:
            try:
                entries = self._run_async(self._read_all_nats())
            except ModuleNotFoundError:
                entries = self._read_all_file()
        else:
            entries = self._read_all_file()
        now = self._now()
        return sorted(
            [entry for entry in entries if entry.expires_at > now],
            key=lambda item: (item.status != "active", item.agent_id, item.started_at),
        )

    def read_by_agent(self, agent_id: str) -> list[AgentSessionEntry]:
        target = agent_id.strip()
        return [entry for entry in self.read_all() if entry.agent_id == target]

    def read_by_target(self, target: str) -> list[AgentSessionEntry]:
        normalized = target.strip()
        return [entry for entry in self.read_all() if entry.current_target == normalized]

    def snapshot(self) -> dict[str, Any]:
        entries = self.read_all()
        summary = {
            "count": len(entries),
            "active": sum(1 for entry in entries if entry.status == "active"),
            "blocked": sum(1 for entry in entries if entry.status == "blocked"),
            "escalated": sum(1 for entry in entries if entry.status == "escalated"),
            "completing": sum(1 for entry in entries if entry.status == "completing"),
            "generated_at": isoformat(self._now()),
        }
        return {"summary": summary, "entries": [entry.as_dict() for entry in entries]}

    def build_entry(
        self,
        *,
        agent_id: str,
        context_id: str | None = None,
        session_label: str | None = None,
        current_phase: str,
        current_target: str | None = None,
        current_workflow_id: str | None = None,
        current_intent_id: str | None = None,
        held_locks: list[str] | None = None,
        held_lanes: list[str] | None = None,
        reserved_budget: dict[str, Any] | None = None,
        batch_id: str | None = None,
        batch_stage: int | None = None,
        step_index: int | None = None,
        step_count: int | None = None,
        progress_pct: float | None = None,
        status: str | None = None,
        blocked_reason: str | None = None,
        error_count: int = 0,
        started_at: datetime | None = None,
        estimated_completion: datetime | None = None,
    ) -> AgentSessionEntry:
        now = self._now()
        resolved_context = (context_id or os.environ.get("LV3_CONTEXT_ID", "").strip() or str(uuid.uuid4())).strip()
        return AgentSessionEntry(
            context_id=resolved_context,
            agent_id=agent_id.strip(),
            session_label=(session_label or f"{agent_id} {resolved_context}").strip(),
            current_phase=current_phase.strip(),
            current_intent_id=current_intent_id,
            current_workflow_id=current_workflow_id,
            current_target=current_target,
            held_locks=list(held_locks or []),
            held_lanes=list(held_lanes or []),
            reserved_budget=dict(reserved_budget or {}),
            batch_id=batch_id,
            batch_stage=batch_stage,
            step_index=step_index,
            step_count=step_count,
            progress_pct=progress_pct,
            last_heartbeat=now,
            status=(status or _status_for_phase(current_phase)).strip(),
            blocked_reason=blocked_reason,
            error_count=error_count,
            started_at=started_at or now,
            estimated_completion=estimated_completion,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )

    def session(
        self,
        *,
        agent_id: str,
        context_id: str | None = None,
        session_label: str | None = None,
        current_phase: str = "bootstrapping",
        current_target: str | None = None,
        current_workflow_id: str | None = None,
    ) -> AgentCoordinationSession:
        entry = self.build_entry(
            agent_id=agent_id,
            context_id=context_id,
            session_label=session_label,
            current_phase=current_phase,
            current_target=current_target,
            current_workflow_id=current_workflow_id,
        )
        return AgentCoordinationSession(store=self, entry=entry, heartbeat_seconds=_default_heartbeat_seconds())

    def _prepare_entry(self, entry: AgentSessionEntry) -> AgentSessionEntry:
        now = self._now()
        if entry.expires_at <= now or (entry.expires_at - entry.last_heartbeat).total_seconds() < self.ttl_seconds - 5:
            return AgentSessionEntry.from_dict(
                {
                    **entry.as_dict(),
                    "last_heartbeat": isoformat(now),
                    "expires_at": isoformat(now + timedelta(seconds=self.ttl_seconds)),
                }
            )
        return entry

    def _load_file_state(self) -> dict[str, dict[str, Any]]:
        if not self.state_file.exists():
            return {}
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}

    def _save_file_state(self, payload: dict[str, dict[str, Any]]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _publish_file(self, entry: AgentSessionEntry) -> None:
        payload = self._load_file_state()
        payload[entry.key] = entry.as_dict()
        self._prune_file_state(payload)
        self._save_file_state(payload)

    def _delete_file(self, *, agent_id: str, context_id: str) -> bool:
        payload = self._load_file_state()
        key = f"{_sanitize_key_component(agent_id)}-{_sanitize_key_component(context_id)}"
        if key not in payload:
            return False
        payload.pop(key, None)
        self._save_file_state(payload)
        return True

    def _read_all_file(self) -> list[AgentSessionEntry]:
        payload = self._load_file_state()
        self._prune_file_state(payload)
        self._save_file_state(payload)
        return [AgentSessionEntry.from_dict(item) for item in payload.values()]

    def _prune_file_state(self, payload: dict[str, dict[str, Any]]) -> None:
        now = self._now()
        stale_keys = []
        for key, value in payload.items():
            expires_at = value.get("expires_at")
            if not isinstance(expires_at, str):
                stale_keys.append(key)
                continue
            try:
                if parse_timestamp(expires_at) <= now:
                    stale_keys.append(key)
            except ValueError:
                stale_keys.append(key)
        for key in stale_keys:
            payload.pop(key, None)

    async def _connect_jetstream(self) -> tuple[Any, Any]:
        from nats.aio.client import Client as NATS

        async def error_cb(error: Exception) -> None:
            recorded_errors.append(error)

        nc = NATS()
        recorded_errors: list[Exception] = []
        setattr(nc, "_lv3_recorded_errors", recorded_errors)
        kwargs: dict[str, Any] = {
            "servers": [self.nats_url],
            "error_cb": error_cb,
            "connect_timeout": 5,
            "allow_reconnect": False,
            "max_reconnect_attempts": 0,
            "reconnect_time_wait": 0,
        }
        if self.nats_credentials:
            kwargs.update(self.nats_credentials)
        await nc.connect(**kwargs)
        return nc, nc.jetstream()

    async def _get_bucket(self, js: Any, *, create: bool) -> Any | None:
        import nats.js.errors

        try:
            return await js.key_value(self.bucket)
        except nats.js.errors.BucketNotFoundError:
            if not create:
                return None
        return await js.create_key_value(
            bucket=self.bucket,
            description="Real-time agent coordination map for active LV3 agent sessions.",
            history=1,
            ttl=self.ttl_seconds,
            direct=True,
        )

    async def _publish_nats(self, entry: AgentSessionEntry) -> None:
        nc, js = await self._connect_jetstream()
        try:
            kv = await self._get_bucket(js, create=True)
            payload = json.dumps(entry.as_dict(), separators=(",", ":")).encode()
            try:
                current = await kv.get(entry.key)
                await kv.update(entry.key, payload, last=current.revision)
            except Exception:
                await kv.put(entry.key, payload)
        finally:
            await nc.drain()

    async def _delete_nats(self, *, agent_id: str, context_id: str) -> bool:
        nc, js = await self._connect_jetstream()
        key = f"{_sanitize_key_component(agent_id)}-{_sanitize_key_component(context_id)}"
        try:
            kv = await self._get_bucket(js, create=False)
            if kv is None:
                return False
            try:
                await kv.delete(key)
                return True
            except Exception:
                return False
        finally:
            await nc.drain()

    async def _read_all_nats(self) -> list[AgentSessionEntry]:
        import nats.js.errors

        nc, js = await self._connect_jetstream()
        try:
            kv = await self._get_bucket(js, create=False)
            if kv is None:
                return []
            try:
                keys = await kv.keys()
            except nats.js.errors.NoKeysError:
                return []
            entries: list[AgentSessionEntry] = []
            for key in sorted(keys):
                try:
                    value = await kv.get(key)
                except (nats.js.errors.KeyNotFoundError, nats.js.errors.KeyDeletedError):
                    continue
                entries.append(AgentSessionEntry.from_dict(json.loads(value.value.decode())))
            return entries
        finally:
            await nc.drain()

    @staticmethod
    def _run_async(coro: Any) -> Any:
        return asyncio.run(coro)


class AgentCoordinationSession:
    def __init__(
        self,
        *,
        store: AgentCoordinationStore,
        entry: AgentSessionEntry,
        heartbeat_seconds: int,
    ) -> None:
        self.store = store
        self.entry = store.publish(entry)
        self.heartbeat_seconds = heartbeat_seconds
        self._running = False
        self._thread: threading.Thread | None = None

    def start_heartbeat(self) -> None:
        if self._running:
            return
        self._running = True

        def runner() -> None:
            while self._running:
                self.heartbeat()
                threading.Event().wait(self.heartbeat_seconds)

        self._thread = threading.Thread(target=runner, name="agent-coordination-heartbeat", daemon=True)
        self._thread.start()

    def stop_heartbeat(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=0.1)
            self._thread = None

    def heartbeat(self) -> AgentSessionEntry:
        self.entry = self.store.publish(
            AgentSessionEntry.from_dict(
                {
                    **self.entry.as_dict(),
                    "last_heartbeat": isoformat(utc_now()),
                    "expires_at": isoformat(utc_now() + timedelta(seconds=self.store.ttl_seconds)),
                }
            )
        )
        return self.entry

    def transition(self, new_phase: str, **updates: Any) -> AgentSessionEntry:
        payload = self.entry.as_dict()
        payload["current_phase"] = new_phase
        payload["status"] = str(updates.pop("status", _status_for_phase(new_phase)))
        for key, value in updates.items():
            if key in {"last_heartbeat", "expires_at", "started_at", "estimated_completion"} and value is not None:
                payload[key] = isoformat(value if isinstance(value, datetime) else parse_timestamp(value))
            else:
                payload[key] = value
        payload["last_heartbeat"] = isoformat(utc_now())
        payload["expires_at"] = isoformat(utc_now() + timedelta(seconds=self.store.ttl_seconds))
        self.entry = self.store.publish(AgentSessionEntry.from_dict(payload))
        return self.entry

    def finish(self, *, final_phase: str = "completing", cleanup: bool = True) -> None:
        try:
            self.transition(final_phase, status="completing", estimated_completion=utc_now())
        finally:
            self.stop_heartbeat()
            if cleanup:
                self.store.delete(self.entry.agent_id, self.entry.context_id)

    def __enter__(self) -> AgentCoordinationSession:
        self.start_heartbeat()
        return self

    def __exit__(self, exc_type, exc, _tb) -> None:
        if exc_type is None:
            self.finish()
            return
        self.transition("blocked", status="blocked", blocked_reason=str(exc), error_count=self.entry.error_count + 1)
        self.stop_heartbeat()
