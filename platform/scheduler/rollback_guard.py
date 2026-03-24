from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RollbackDepthResult:
    depth: int
    exceeded: bool
    chain: tuple[str, ...]
    reason: str | None = None


class RollbackGuard:
    def __init__(self, reader: Any | None = None, *, max_chain_length: int = 32) -> None:
        self._reader = reader
        self._max_chain_length = max_chain_length

    def check_depth(
        self,
        parent_actor_intent_id: str | None,
        *,
        max_depth: int,
    ) -> RollbackDepthResult:
        if not parent_actor_intent_id:
            return RollbackDepthResult(depth=0, exceeded=False, chain=())
        if self._reader is None:
            return RollbackDepthResult(
                depth=1,
                exceeded=False,
                chain=(parent_actor_intent_id,),
                reason="ledger reader unavailable",
            )

        visited = {parent_actor_intent_id}
        chain = [parent_actor_intent_id]
        current = parent_actor_intent_id
        depth = 1

        while current and depth < self._max_chain_length:
            events = self._reader.events_by_intent(current, limit=20)
            if not events:
                break
            metadata = next(
                (
                    event.get("metadata")
                    for event in events
                    if isinstance(event.get("metadata"), dict)
                ),
                {},
            )
            if not isinstance(metadata, dict):
                break
            parent = metadata.get("parent_actor_intent_id") or metadata.get("rollback_parent_intent_id")
            if not isinstance(parent, str) or not parent.strip():
                break
            if parent in visited:
                return RollbackDepthResult(
                    depth=depth,
                    exceeded=True,
                    chain=tuple(chain),
                    reason="rollback intent chain contains a cycle",
                )
            visited.add(parent)
            chain.append(parent)
            current = parent
            depth += 1

        return RollbackDepthResult(
            depth=depth,
            exceeded=depth > max_depth,
            chain=tuple(chain),
        )
