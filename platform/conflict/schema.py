from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_CLAIM_ACCESS = {"read", "write", "exclusive"}


@dataclass(frozen=True)
class ResourceClaim:
    resource: str
    access: str

    def __post_init__(self) -> None:
        if self.access not in ALLOWED_CLAIM_ACCESS:
            raise ValueError(f"unsupported resource claim access '{self.access}'")
        if not self.resource.strip():
            raise ValueError("resource claims must name a resource")

    def as_dict(self) -> dict[str, str]:
        return {"resource": self.resource, "access": self.access}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ResourceClaim:
        return cls(
            resource=str(payload.get("resource", "")).strip(),
            access=str(payload.get("access", "")).strip(),
        )


@dataclass(frozen=True)
class ConflictWarning:
    conflict_type: str
    message: str
    conflicting_intent_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "conflict_type": self.conflict_type,
            "message": self.message,
        }
        if self.conflicting_intent_id:
            payload["conflicting_intent_id"] = self.conflicting_intent_id
        return payload


@dataclass(frozen=True)
class ConflictCheckResult:
    status: str
    resolution: str | None = None
    conflicting_intent_id: str | None = None
    conflicting_actor: str | None = None
    conflict_type: str | None = None
    message: str | None = None
    dedup_output: Any = None
    resource_claims: list[ResourceClaim] = field(default_factory=list)
    warnings: list[ConflictWarning] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "resource_claims": [claim.as_dict() for claim in self.resource_claims],
            "warnings": [warning.as_dict() for warning in self.warnings],
        }
        if self.resolution:
            payload["resolution"] = self.resolution
        if self.conflicting_intent_id:
            payload["conflicting_intent_id"] = self.conflicting_intent_id
        if self.conflicting_actor:
            payload["conflicting_actor"] = self.conflicting_actor
        if self.conflict_type:
            payload["conflict_type"] = self.conflict_type
        if self.message:
            payload["message"] = self.message
        if self.dedup_output is not None:
            payload["dedup_output"] = self.dedup_output
        return payload
