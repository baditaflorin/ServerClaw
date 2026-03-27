from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time

from .hierarchy import resolve_timeout_seconds


class TimeoutExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class TimeoutContext:
    total_seconds: float
    layer: str
    repo_root: Path | None = None
    started_at: float = field(default_factory=time.monotonic)

    @classmethod
    def for_layer(
        cls,
        layer: str,
        requested_seconds: int | float | None = None,
        *,
        repo_root: Path | None = None,
    ) -> "TimeoutContext":
        return cls(
            total_seconds=resolve_timeout_seconds(layer, requested_seconds),
            layer=layer,
            repo_root=repo_root,
        )

    @property
    def deadline(self) -> float:
        return self.started_at + self.total_seconds

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def timeout_for(
        self,
        layer: str,
        requested_seconds: int | float | None = None,
        *,
        reserve_seconds: float = 0.0,
        minimum_seconds: float = 0.5,
    ) -> float:
        layer_limit = resolve_timeout_seconds(layer, requested_seconds)
        budget = min(layer_limit, self.remaining() - reserve_seconds)
        if budget < minimum_seconds:
            raise TimeoutExceeded(
                f"insufficient time remaining for {layer}: {self.remaining():.3f}s remaining"
            )
        return budget

    def child(
        self,
        layer: str,
        requested_seconds: int | float | None = None,
        *,
        reserve_seconds: float = 0.0,
        minimum_seconds: float = 0.5,
    ) -> "TimeoutContext":
        return TimeoutContext(
            total_seconds=self.timeout_for(
                layer,
                requested_seconds,
                reserve_seconds=reserve_seconds,
                minimum_seconds=minimum_seconds,
            ),
            layer=layer,
            repo_root=self.repo_root,
        )

    def __enter__(self) -> "TimeoutContext":
        if self.remaining() <= 0:
            raise TimeoutExceeded(f"deadline already exceeded at layer {self.layer}")
        return self

    def __exit__(self, *_args: object) -> None:
        return None
