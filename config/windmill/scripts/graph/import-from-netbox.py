#!/usr/bin/env python3

from __future__ import annotations

import os

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


GRAPH_RUNTIME_DEPENDENCIES = ("pyyaml", "psycopg[binary]")
UV_RUNTIME_FLAGS = ("--isolated", "--no-project")


def _requires_uv_runtime(exc: BaseException) -> bool:
    if isinstance(exc, ModuleNotFoundError):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc)
        return "psycopg is required for postgres" in message or "Missing dependency: PyYAML" in message
    return False


def _load_graph_dependencies(repo_root: Path):
    for candidate in (repo_root / "scripts", repo_root):
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
    if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
        del sys.modules["platform"]

    from platform.graph import rebuild_graph_from_repo

    return rebuild_graph_from_repo


def _run_via_uv(script_path: Path, repo_root: Path, dsn: str | None, world_state_dsn: str | None) -> dict[str, Any]:
    command = ["uv", "run", *UV_RUNTIME_FLAGS]
    for dependency in GRAPH_RUNTIME_DEPENDENCIES:
        command.extend(["--with", dependency])
    command.extend(
        [
            "python3",
            str(script_path),
            "--repo-path",
            str(repo_root),
        ]
    )
    if dsn:
        command.extend(["--dsn", dsn])
    if world_state_dsn:
        command.extend(["--world-state-dsn", world_state_dsn])

    result = subprocess.run(command, cwd=script_path.parent, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if result.stdout.strip():
        try:
            payload["result"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return payload


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
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
    try:
        rebuild_graph_from_repo = _load_graph_dependencies(repo_root)
        result = rebuild_graph_from_repo(
            repo_root=repo_root,
            dsn=dsn,
            world_state_dsn=world_state_dsn or dsn,
        )
    except (ModuleNotFoundError, RuntimeError) as exc:
        if not _requires_uv_runtime(exc):
            raise
        return _run_via_uv(
            repo_root / "config" / "windmill" / "scripts" / "graph" / "import-from-netbox.py",
            repo_root,
            dsn,
            world_state_dsn,
        )
    result["source"] = "netbox_topology"
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild the ADR 0117 graph from NetBox world state.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--dsn")
    parser.add_argument("--world-state-dsn")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path, dsn=args.dsn, world_state_dsn=args.world_state_dsn), indent=2))
