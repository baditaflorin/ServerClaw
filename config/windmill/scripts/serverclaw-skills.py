#!/usr/bin/env python3
"""Windmill wrapper for the ADR 0257 ServerClaw skill-pack resolver."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(
    workspace_id: str | None = None,
    skill_id: str | None = None,
    include_imported: bool = True,
    include_prompt_manifest: bool = True,
    repo_path: str = "/srv/proxmox_florin_server",
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "serverclaw_skill_packs.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    module = load_module("serverclaw_skill_packs_worker", workflow)
    result = module.list_serverclaw_skill_packs(
        repo_root=repo_root,
        workspace_id=workspace_id,
        skill_id=skill_id,
        include_imported=include_imported,
        include_prompt_manifest=include_prompt_manifest,
    )
    return {"status": "ok", "result": result}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0257 ServerClaw skill-pack resolver from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--workspace-id")
    parser.add_argument("--skill-id")
    parser.add_argument("--include-imported", action="store_true")
    parser.add_argument("--no-prompt-manifest", action="store_true")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(
        json.dumps(
            main(
                workspace_id=args.workspace_id,
                skill_id=args.skill_id,
                include_imported=args.include_imported,
                include_prompt_manifest=not args.no_prompt_manifest,
                repo_path=args.repo_path,
            ),
            indent=2,
            sort_keys=True,
        )
    )
