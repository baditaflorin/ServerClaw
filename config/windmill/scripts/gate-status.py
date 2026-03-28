#!/usr/bin/env python3
"""Windmill wrapper for the repository validation gate status."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def _load_gate_status_module(repo_root: Path):
    script_path = repo_root / "scripts" / "gate_status.py"
    spec = importlib.util.spec_from_file_location("gate_status_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load gate status script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "gate_status.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "gate status script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    module = _load_gate_status_module(repo_root)
    payload = module.build_status_payload(
        manifest_path=repo_root / "config" / "validation-gate.json",
        last_run_path=repo_root / ".local" / "validation-gate" / "last-run.json",
        post_merge_run_path=repo_root / ".local" / "validation-gate" / "post-merge-last-run.json",
        bypass_dir=repo_root / "receipts" / "gate-bypasses",
    )
    return {
        "status": "ok",
        "gate_status": payload,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show repository validation gate status from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
