#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
from typing import Any

from platform.graph import rebuild_graph_from_repo


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    dsn: str | None = None,
    world_state_dsn: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }
    result = rebuild_graph_from_repo(
        repo_root=repo_root,
        dsn=dsn,
        world_state_dsn=world_state_dsn or dsn,
    )
    result["source"] = "netbox_topology"
    return result
