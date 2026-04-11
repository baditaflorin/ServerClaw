#!/usr/bin/env python3
"""Windmill wrapper for ADR 0189 network impairment matrix rendering."""

from __future__ import annotations

import os

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _parse_json(stdout: str) -> dict:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("network impairment matrix wrapper expected a JSON object")
    return payload


def _load_repo_script(repo_root: Path):
    scripts_dir = repo_root / "scripts"
    script_path = scripts_dir / "network_impairment_matrix.py"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("network_impairment_matrix_runtime", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load network impairment matrix script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _execute_via_uv(
    *,
    repo_root: Path,
    report_script: Path,
    target_class: str,
    service: str,
    report_file: str,
) -> dict:
    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        str(report_script),
        "--repo-path",
        str(repo_root),
        "--format",
        "json",
    ]
    if target_class.strip():
        command.extend(["--target-class", target_class])
    if service.strip():
        command.extend(["--service", service])
    if report_file.strip():
        command.extend(["--report-file", report_file])

    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return {
            "status": "error",
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    return _parse_json(result.stdout)


def _should_fallback_to_uv(exc: Exception) -> bool:
    if isinstance(exc, ModuleNotFoundError):
        return exc.name == "yaml"
    return isinstance(exc, RuntimeError) and "PyYAML is required" in str(exc)


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    target_class: str = "",
    service: str = "",
    report_file: str = "",
) -> dict:
    repo_root = Path(repo_path)
    report_script = repo_root / "scripts" / "network_impairment_matrix.py"
    if not report_script.exists():
        return {
            "status": "blocked",
            "reason": "network impairment matrix script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    try:
        module = _load_repo_script(repo_root)
        return module.main(
            repo_path=str(repo_root),
            target_class=target_class,
            service=service,
            output_format="json",
            report_file=report_file or None,
        )
    except Exception as exc:
        if not _should_fallback_to_uv(exc):
            raise

    return _execute_via_uv(
        repo_root=repo_root,
        report_script=report_script,
        target_class=target_class,
        service=service,
        report_file=report_file,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render ADR 0189 from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--target-class", default="")
    parser.add_argument("--service", default="")
    parser.add_argument("--report-file", default="")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                target_class=args.target_class,
                service=args.service,
                report_file=args.report_file,
            ),
            indent=2,
            sort_keys=True,
        )
    )
