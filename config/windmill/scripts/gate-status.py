#!/usr/bin/env python3
"""Windmill wrapper for the repository validation gate status."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
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


def _yaml_module_available() -> bool:
    return importlib.util.find_spec("yaml") is not None


@contextmanager
def _gate_status_import_context(
    repo_root: Path,
    *,
    inject_waiver_fallback: bool = False,
) -> Iterator[None]:
    repo_root_str = str(repo_root)
    scripts_dir = str(repo_root / "scripts")
    added_paths: list[str] = []
    for candidate in (repo_root_str, scripts_dir):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
            added_paths.append(candidate)

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
        for candidate in reversed(added_paths):
            try:
                sys.path.remove(candidate)
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


def _load_gate_bypass_waivers_module(repo_root: Path):
    with _gate_status_import_context(repo_root):
        try:
            return importlib.import_module("gate_bypass_waivers")
        except ModuleNotFoundError as exc:
            if exc.name != "gate_bypass_waivers":
                raise

    with _gate_status_import_context(repo_root, inject_waiver_fallback=True):
        return importlib.import_module("gate_bypass_waivers")


def _build_waiver_summary(repo_root: Path) -> dict:
    gate_bypass_waivers = _load_gate_bypass_waivers_module(repo_root)
    summary = gate_bypass_waivers.summarize_receipts(directory=repo_root / "receipts" / "gate-bypasses")
    return {
        "totals": summary["totals"],
        "latest_receipt": summary["latest_receipt"],
        "open_waivers": summary["open_waivers"],
        "expiring_soon": summary["expiring_soon"],
        "warnings": summary["warnings"],
        "release_blockers": summary["release_blockers"],
        "invalid_receipts": summary["invalid_receipts"],
    }


def _normalize_status_payload(repo_root: Path, payload: dict) -> dict:
    normalized = dict(payload)
    if "waiver_summary" not in normalized:
        normalized["waiver_summary"] = _build_waiver_summary(repo_root)
    return normalized


def _run_gate_status_script_with_helper(
    repo_root: Path,
    *,
    manifest_path: Path,
    last_run_path: Path,
    remote_validate_run_path: Path,
    post_merge_run_path: Path,
    bypass_dir: Path,
) -> dict:
    helper_path = repo_root / "scripts" / "run_python_with_packages.sh"
    script_path = repo_root / "scripts" / "gate_status.py"
    if not helper_path.exists():
        return {
            "status": "blocked",
            "reason": "gate status helper is missing from the worker checkout",
            "expected_helper_path": str(helper_path),
        }

    command = [
        str(helper_path),
        "pyyaml",
        "--",
        str(script_path),
        "--manifest",
        str(manifest_path),
        "--last-run",
        str(last_run_path),
        "--remote-validate-run",
        str(remote_validate_run_path),
        "--post-merge-run",
        str(post_merge_run_path),
        "--bypass-dir",
        str(bypass_dir),
        "--format",
        "json",
    ]
    result = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "status": "error",
            "reason": "gate status helper execution failed",
            "command": " ".join(command),
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "reason": "gate status helper returned invalid json",
            "command": " ".join(command),
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "gate_status.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "gate status script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    payload_kwargs = {
        "manifest_path": repo_root / "config" / "validation-gate.json",
        "last_run_path": repo_root / ".local" / "validation-gate" / "last-run.json",
        "remote_validate_run_path": repo_root / ".local" / "validation-gate" / "remote-validate-last-run.json",
        "post_merge_run_path": repo_root / ".local" / "validation-gate" / "post-merge-last-run.json",
        "bypass_dir": repo_root / "receipts" / "gate-bypasses",
    }

    if _yaml_module_available():
        module = _load_gate_status_module(repo_root)
        accepted_kwargs = inspect.signature(module.build_status_payload).parameters
        payload = module.build_status_payload(**{name: value for name, value in payload_kwargs.items() if name in accepted_kwargs})
    else:
        helper_payload = _run_gate_status_script_with_helper(
            repo_root,
            **payload_kwargs,
        )
        if helper_payload.get("status") in {"blocked", "error"}:
            return helper_payload
        payload = helper_payload

    payload = _normalize_status_payload(repo_root, payload)
    return {
        "status": "ok",
        "gate_status": payload,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show repository validation gate status from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
