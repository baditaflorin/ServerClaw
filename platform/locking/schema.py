from __future__ import annotations

from dataclasses import dataclass, field
from platform.enum_compat import StrEnum
from typing import Any


class LockType(StrEnum):
    SHARED = "shared"
    EXCLUSIVE = "exclusive"
    INTENT = "intent"


@dataclass(frozen=True)
class LockEntry:
    lock_id: str
    resource_path: str
    lock_type: LockType
    holder: str
    context_id: str | None = None
    acquired_at: str = ""
    expires_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.lock_id.strip():
            raise ValueError("lock_id must be a non-empty string")
        if not self.resource_path.strip():
            raise ValueError("resource_path must be a non-empty string")
        if not self.holder.strip():
            raise ValueError("holder must be a non-empty string")

    def as_dict(self) -> dict[str, Any]:
        return {
            "lock_id": self.lock_id,
            "resource_path": self.resource_path,
            "lock_type": self.lock_type.value,
            "holder": self.holder,
            "context_id": self.context_id,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LockEntry:
        return cls(
            lock_id=str(payload.get("lock_id", "")).strip(),
            resource_path=str(payload.get("resource_path", "")).strip(),
            lock_type=LockType(str(payload.get("lock_type", LockType.EXCLUSIVE.value)).strip()),
            holder=str(payload.get("holder", "")).strip(),
            context_id=_optional_str(payload.get("context_id")),
            acquired_at=str(payload.get("acquired_at", "")).strip(),
            expires_at=str(payload.get("expires_at", "")).strip(),
            metadata=dict(payload.get("metadata", {}) or {}),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None
