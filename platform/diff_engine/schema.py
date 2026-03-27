from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChangedObject:
    surface: str
    object_id: str
    change_kind: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    confidence: str
    reversible: bool
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "surface": self.surface,
            "object_id": self.object_id,
            "change_kind": self.change_kind,
            "before": self.before,
            "after": self.after,
            "confidence": self.confidence,
            "reversible": self.reversible,
        }
        if self.notes:
            payload["notes"] = self.notes
        return payload


@dataclass(frozen=True)
class SemanticDiff:
    intent_id: str
    computed_at: str
    changed_objects: tuple[ChangedObject, ...]
    total_changes: int
    irreversible_count: int
    unknown_count: int
    adapters_used: tuple[str, ...]
    elapsed_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "computed_at": self.computed_at,
            "changed_objects": [item.as_dict() for item in self.changed_objects],
            "total_changes": self.total_changes,
            "irreversible_count": self.irreversible_count,
            "unknown_count": self.unknown_count,
            "adapters_used": list(self.adapters_used),
            "elapsed_ms": self.elapsed_ms,
        }


def unknown_object(*, surface: str, object_id: str, notes: str) -> ChangedObject:
    return ChangedObject(
        surface=surface,
        object_id=object_id,
        change_kind="unknown",
        before=None,
        after=None,
        confidence="unknown",
        reversible=False,
        notes=notes,
    )
