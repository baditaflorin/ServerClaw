#!/usr/bin/env python3
"""Windmill wrapper for the repository validation gate status."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


def default_waiver_summary(receipt_dir: Path, reason: str | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "generated_at": None,
        "catalog_path": None,
        "receipt_dir": str(receipt_dir),
        "policy": None,
        "totals": {
            "all_receipts": 0,
            "legacy_receipts": 0,
            "compliant_receipts": 0,
            "open_waivers": 0,
            "expired_waivers": 0,
            "invalid_receipts": 0,
        },
        "latest_receipt": None,
        "open_waivers": [],
        "expiring_soon": [],
        "reason_codes": [],
        "warnings": [],
        "release_blockers": [],
        "invalid_receipts": [],
    }
    if reason:
        summary["summary_error"] = reason
    return summary


def load_repo_module(repo_root: Path, relative_path: str, module_name: str):
    module_path = repo_root / relative_path
    if not module_path.is_file():
        raise FileNotFoundError(f"missing module at {module_path}")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    repo_root_str = str(repo_root)
    added_repo_root = False
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
        added_repo_root = True
    try:
        spec.loader.exec_module(module)
    finally:
        if added_repo_root:
            try:
                sys.path.remove(repo_root_str)
            except ValueError:
                pass
    return module


def ensure_waiver_summary(repo_root: Path, gate_status: dict[str, Any]) -> None:
    existing = gate_status.get("waiver_summary")
    if isinstance(existing, dict):
        return

    receipt_dir = repo_root / "receipts" / "gate-bypasses"
    try:
        module = load_repo_module(
            repo_root=repo_root,
            relative_path="scripts/gate_bypass_waivers.py",
            module_name=f"windmill_gate_bypass_waivers_{abs(hash(repo_root.resolve()))}",
        )
        summary = module.summarize_receipts(directory=receipt_dir)
        gate_status["waiver_summary"] = summary if isinstance(summary, dict) else default_waiver_summary(receipt_dir)
    except Exception as exc:
        gate_status["waiver_summary"] = default_waiver_summary(receipt_dir, reason=str(exc))


def build_gate_status_command(repo_root: Path) -> list[str]:
    script_path = repo_root / "scripts" / "gate_status.py"
    helper_path = repo_root / "scripts" / "run_python_with_packages.sh"
    if helper_path.is_file():
        return [str(helper_path), "pyyaml", "--", str(script_path), "--format", "json"]
    return [sys.executable, str(script_path), "--format", "json"]


def main(repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server")) -> dict[str, Any]:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "gate_status.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "gate status script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = build_gate_status_command(repo_root)
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=dict(os.environ),
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload: dict[str, Any] = {
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    if completed.returncode != 0:
        payload.update(
            {
                "status": "error",
                "reason": "gate status command failed",
            }
        )
        return payload
    if not stdout:
        payload.update(
            {
                "status": "error",
                "reason": "gate status command returned empty stdout",
            }
        )
        return payload
    try:
        gate_status = json.loads(stdout)
    except json.JSONDecodeError as exc:
        payload.update(
            {
                "status": "error",
                "reason": "gate status command returned non-JSON stdout",
                "parse_error": str(exc),
            }
        )
        return payload
    if not isinstance(gate_status, dict):
        payload.update(
            {
                "status": "error",
                "reason": "gate status command did not return a JSON object",
                "gate_status": gate_status,
            }
        )
        return payload
    ensure_waiver_summary(repo_root, gate_status)
    payload.update(
        {
            "status": "ok",
            "gate_status": gate_status,
        }
    )
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show repository validation gate status from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
