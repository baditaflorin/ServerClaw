from __future__ import annotations

import hashlib
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from platform.concurrency import default_state_path, isoformat, locked_json_state, parse_timestamp, utc_now

from .schema import LockEntry, LockType


LOCK_REGISTRY_STATE_ENV = "LV3_LOCK_REGISTRY_PATH"
LOCK_REGISTRY_STATE_SUBPATH = Path("lv3-concurrency") / "lock-registry.json"


class ResourceLocked(RuntimeError):
    def __init__(self, resource_path: str, blockers: list[LockEntry]):
        message = ", ".join(f"{entry.holder}:{entry.resource_path}" for entry in blockers) or "unknown holder"
        super().__init__(f"resource '{resource_path}' is locked by {message}")
        self.resource_path = resource_path
        self.blockers = blockers


class ResourceLockRegistry:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        state_path: Path | None = None,
        now_fn: Any | None = None,
    ) -> None:
        self._state_path = state_path or default_state_path(
            env_var=LOCK_REGISTRY_STATE_ENV,
            repo_root=repo_root,
            state_subpath=LOCK_REGISTRY_STATE_SUBPATH,
        )
        self._now = now_fn or utc_now

    def acquire(
        self,
        resource_path: str,
        lock_type: LockType | str,
        holder: str,
        *,
        context_id: str | None = None,
        ttl_seconds: int = 300,
        wait_seconds: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> LockEntry:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        normalized_type = lock_type if isinstance(lock_type, LockType) else LockType(str(lock_type))
        deadline = time.monotonic() + max(wait_seconds, 0)
        while True:
            with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
                self._purge_locked(state)
                locks = self._entries_locked(state)
                existing = self._find_duplicate(locks, resource_path=resource_path, holder=holder, lock_type=normalized_type)
                if existing is not None:
                    refreshed = LockEntry(
                        lock_id=existing.lock_id,
                        resource_path=existing.resource_path,
                        lock_type=existing.lock_type,
                        holder=existing.holder,
                        context_id=context_id or existing.context_id,
                        acquired_at=existing.acquired_at,
                        expires_at=isoformat(self._now() + timedelta(seconds=ttl_seconds)),
                        metadata=dict(existing.metadata) | dict(metadata or {}),
                    )
                    state["locks"][existing.lock_id] = refreshed.as_dict()
                    return refreshed
                entry = LockEntry(
                    lock_id=self._lock_id(resource_path=resource_path, holder=holder, lock_type=normalized_type),
                    resource_path=resource_path.strip(),
                    lock_type=normalized_type,
                    holder=holder.strip(),
                    context_id=context_id,
                    acquired_at=isoformat(self._now()),
                    expires_at=isoformat(self._now() + timedelta(seconds=ttl_seconds)),
                    metadata=dict(metadata or {}),
                )
                blockers = self._conflicting_entries(locks, entry)
                if not blockers:
                    state["locks"][entry.lock_id] = entry.as_dict()
                    return entry
            if time.monotonic() >= deadline:
                raise ResourceLocked(resource_path, blockers)
            time.sleep(0.2)

    def read_all(self) -> list[LockEntry]:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            self._purge_locked(state)
            locks = self._entries_locked(state)
        return sorted(locks, key=lambda entry: (entry.resource_path, entry.holder, entry.lock_id))

    def get_holder(self, resource_path: str, *, exclude_holder: str | None = None) -> str | None:
        candidates = [entry for entry in self.read_all() if self._resource_related(entry.resource_path, resource_path)]
        if exclude_holder is not None:
            candidates = [entry for entry in candidates if entry.holder != exclude_holder]
        if not candidates:
            return None
        ordered = sorted(candidates, key=lambda entry: self._holder_order(entry.lock_type))
        return ordered[0].holder

    def release(self, *, lock_id: str | None = None, resource_path: str | None = None, holder: str | None = None) -> int:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            self._purge_locked(state)
            to_delete = []
            for current_lock_id, payload in state["locks"].items():
                if not isinstance(payload, dict):
                    to_delete.append(current_lock_id)
                    continue
                entry = LockEntry.from_dict(payload)
                if lock_id and current_lock_id != lock_id:
                    continue
                if resource_path and entry.resource_path != resource_path:
                    continue
                if holder and entry.holder != holder:
                    continue
                to_delete.append(current_lock_id)
            for current_lock_id in to_delete:
                state["locks"].pop(current_lock_id, None)
            return len(to_delete)

    def release_all(self, holder: str) -> int:
        return self.release(holder=holder)

    def heartbeat(self, lock_id: str, *, ttl_seconds: int = 300) -> LockEntry | None:
        with locked_json_state(self._state_path, default_factory=self._empty_state) as state:
            self._purge_locked(state)
            payload = state["locks"].get(lock_id)
            if not isinstance(payload, dict):
                return None
            entry = LockEntry.from_dict(payload)
            updated = LockEntry(
                lock_id=entry.lock_id,
                resource_path=entry.resource_path,
                lock_type=entry.lock_type,
                holder=entry.holder,
                context_id=entry.context_id,
                acquired_at=entry.acquired_at,
                expires_at=isoformat(self._now() + timedelta(seconds=ttl_seconds)),
                metadata=dict(entry.metadata),
            )
            state["locks"][lock_id] = updated.as_dict()
            return updated

    def _entries_locked(self, state: dict[str, Any]) -> list[LockEntry]:
        return [LockEntry.from_dict(payload) for payload in state["locks"].values() if isinstance(payload, dict)]

    def _purge_locked(self, state: dict[str, Any]) -> None:
        now = self._now()
        expired = []
        for lock_id, payload in state.setdefault("locks", {}).items():
            if not isinstance(payload, dict):
                expired.append(lock_id)
                continue
            expires_at = payload.get("expires_at")
            if not expires_at or parse_timestamp(str(expires_at)) <= now:
                expired.append(lock_id)
        for lock_id in expired:
            state["locks"].pop(lock_id, None)

    @staticmethod
    def _holder_order(lock_type: LockType) -> int:
        if lock_type is LockType.EXCLUSIVE:
            return 0
        if lock_type is LockType.INTENT:
            return 1
        return 2

    @staticmethod
    def _lock_id(*, resource_path: str, holder: str, lock_type: LockType) -> str:
        digest = hashlib.sha256(f"{resource_path}|{holder}|{lock_type.value}".encode("utf-8")).hexdigest()
        return digest[:20]

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"schema_version": "1.0.0", "locks": {}}

    @staticmethod
    def _resource_related(left: str, right: str) -> bool:
        return (
            left == right
            or left.startswith(f"{right}/")
            or right.startswith(f"{left}/")
        )

    @staticmethod
    def _find_duplicate(
        locks: list[LockEntry],
        *,
        resource_path: str,
        holder: str,
        lock_type: LockType,
    ) -> LockEntry | None:
        for entry in locks:
            if entry.resource_path == resource_path and entry.holder == holder and entry.lock_type is lock_type:
                return entry
        return None

    def _conflicting_entries(self, locks: list[LockEntry], candidate: LockEntry) -> list[LockEntry]:
        return [
            entry
            for entry in locks
            if entry.holder != candidate.holder
            and self._resource_related(entry.resource_path, candidate.resource_path)
            and self._lock_types_conflict(candidate.lock_type, entry.lock_type)
        ]

    @staticmethod
    def _lock_types_conflict(requested: LockType, existing: LockType) -> bool:
        if requested is LockType.SHARED:
            return existing is LockType.EXCLUSIVE
        if requested is LockType.INTENT:
            return existing is LockType.EXCLUSIVE
        if requested is LockType.EXCLUSIVE:
            return existing in {LockType.SHARED, LockType.EXCLUSIVE, LockType.INTENT}
        return True
