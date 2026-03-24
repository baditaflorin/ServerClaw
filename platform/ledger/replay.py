from __future__ import annotations

from typing import Any, Callable

from .reader import LedgerReader


class LedgerReplayer:
    def __init__(
        self,
        *,
        reader: LedgerReader | None = None,
        dsn: str | None = None,
        connection: Any = None,
        connect: Callable[[str], Any] | None = None,
    ) -> None:
        self._reader = reader or LedgerReader(dsn=dsn, connection=connection, connect=connect)

    def slice(
        self,
        *,
        target_kind: str,
        target_id: str,
        from_ts: str,
        to_ts: str,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        return self._reader.events_by_target(
            target_kind=target_kind,
            target_id=target_id,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
        )

    def project_state(self, subject: str, *, at: str) -> Any:
        if ":" not in subject:
            raise ValueError("subject must use '<target_kind>:<target_id>' format")
        target_kind, target_id = subject.split(":", 1)
        if target_kind not in {"service", "vm"}:
            raise NotImplementedError(f"state projection is not implemented for target kind: {target_kind}")

        events = self._reader.events_by_target(
            target_kind=target_kind,
            target_id=target_id,
            to_ts=at,
            limit=5000,
        )
        projected_state = None
        for event in events:
            if event.get("after_state") is not None:
                projected_state = event["after_state"]
            elif projected_state is None and event.get("before_state") is not None:
                projected_state = event["before_state"]
        return projected_state
