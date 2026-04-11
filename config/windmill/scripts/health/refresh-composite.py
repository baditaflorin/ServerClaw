#!/usr/bin/env python3

from __future__ import annotations

import os

from pathlib import Path

from platform.health import HealthCompositeClient
from platform.world_state.workers import publish_refresh_event_best_effort


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    dsn: str | None = None,
    world_state_dsn: str | None = None,
    ledger_dsn: str | None = None,
    publish_nats: bool = True,
) -> dict[str, object]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    published: list[dict[str, object]] = []

    def publisher(subject: str, payload: dict[str, object]) -> None:
        if publish_nats:
            published.append(publish_refresh_event_best_effort(subject, payload))

    client = HealthCompositeClient(
        repo_root=repo_root,
        dsn=dsn,
        world_state_dsn=world_state_dsn or dsn,
        ledger_dsn=ledger_dsn or dsn,
    )
    result = client.refresh(event_publisher=publisher)
    result["publish_results"] = published
    return result
