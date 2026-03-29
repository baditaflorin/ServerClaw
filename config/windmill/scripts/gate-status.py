#!/usr/bin/env python3
"""Windmill wrapper for the repository validation gate status."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
import types
from typing import Iterator


def _build_gate_bypass_waivers_fallback():
    module = types.ModuleType("gate_bypass_waivers")

    def summarize_receipts(*, directory: Path):
        return {
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
            "warnings": [],
            "release_blockers": [],
            "invalid_receipts": [],
            "reason_codes": [],
            "receipt_dir": str(directory),
        }

    module.summarize_receipts = summarize_receipts
    return module


@contextmanager
def _gate_status_import_context(
    repo_root: Path,
    *,
    inject_waiver_fallback: bool = False,
) -> Iterator[None]:
    scripts_dir = str(repo_root / "scripts")
    added_scripts_dir = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        added_scripts_dir = True

    previous_gate_bypass_waivers = sys.modules.pop("gate_bypass_waivers", None)
    injected_fallback = False
    if inject_waiver_fallback:
        sys.modules["gate_bypass_waivers"] = _build_gate_bypass_waivers_fallback()
        injected_fallback = True

    try:
        yield
    finally:
        sys.modules.pop("gate_bypass_waivers", None)
        if previous_gate_bypass_waivers is not None:
            sys.modules["gate_bypass_waivers"] = previous_gate_bypass_waivers
        if added_scripts_dir:
            try:
                sys.path.remove(scripts_dir)
            except ValueError:
                pass


def _load_gate_status_module_once(repo_root: Path):
    script_path = repo_root / "scripts" / "gate_status.py"
    spec = importlib.util.spec_from_file_location("gate_status_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load gate status script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_gate_status_module(repo_root: Path):
    with _gate_status_import_context(repo_root):
        try:
            return _load_gate_status_module_once(repo_root)
        except ModuleNotFoundError as exc:
            if exc.name != "gate_bypass_waivers":
                raise

    with _gate_status_import_context(repo_root, inject_waiver_fallback=True):
        return _load_gate_status_module_once(repo_root)


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
        remote_validate_run_path=repo_root / ".local" / "validation-gate" / "remote-validate-last-run.json",
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
