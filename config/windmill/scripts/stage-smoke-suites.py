#!/usr/bin/env python3
"""Windmill wrapper for the repo-managed ADR 0251 smoke suites."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path


def default_report_file(service: str, environment: str) -> str:
    safe_service = service.strip().replace("/", "-") or "service"
    safe_environment = environment.strip().replace("/", "-") or "environment"
    return str(Path(tempfile.gettempdir()) / f"lv3-stage-smoke-suites-{safe_environment}-{safe_service}.json")


def _resolve_repo_root(repo_path: str | None = None) -> Path:
    """Locate the worker checkout when Windmill omits its environment hints."""
    if repo_path:
        return Path(repo_path)

    candidates: list[Path] = []
    for env_name in ("PLATFORM_REPO_ROOT", "LV3_WINDMILL_REPO_ROOT", "LV3_REPO_ROOT"):
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append(Path(value))

    cwd = Path.cwd()
    candidates.append(cwd)
    candidates.extend(cwd.parents)
    for base in (Path("/srv"), Path("/workspace"), Path("/workspaces")):
        try:
            candidates.extend(path for path in base.iterdir() if path.is_dir())
        except OSError:
            continue

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            resolved = candidate.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "scripts" / "stage_smoke_suites.py").is_file():
            return resolved
    return Path("/srv/platform_server")


def main(
    service: str = "windmill",
    environment: str = "production",
    repo_path: str | None = None,
    report_file: str = "",
    suite_ids: str = "",
):
    repo_root = _resolve_repo_root(repo_path)
    script_path = repo_root / "scripts" / "stage_smoke_suites.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "stage smoke suite runner is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
            "service": service,
            "environment": environment,
        }

    command = [
        "python3",
        str(script_path),
        "--service",
        service,
        "--environment",
        environment,
    ]
    resolved_report_file = report_file.strip() or default_report_file(service, environment)
    command.extend(["--report-file", resolved_report_file])
    for suite_id in [item.strip() for item in suite_ids.split(",") if item.strip()]:
        command.extend(["--suite-id", suite_id])

    command_env = dict(os.environ)
    command_env.update(load_integration_env_overrides(repo_root))
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=command_env,
    )
    payload = {
        "status": "ok" if completed.returncode == 0 else "error",
        "service": service,
        "environment": environment,
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": completed.returncode,
        "report_file": resolved_report_file,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    if completed.stdout.strip():
        try:
            payload["result"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            pass
    return payload


def load_integration_env_overrides(repo_root: Path) -> dict[str, str]:
    helper_path = repo_root / "config" / "windmill" / "scripts" / "windmill_integration_env.py"
    if not helper_path.exists():
        return {}
    spec = importlib.util.spec_from_file_location("lv3_windmill_integration_env", helper_path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resolver = getattr(module, "integration_env_overrides", None)
    if not callable(resolver):
        return {}
    overrides = resolver(repo_root)
    return overrides if isinstance(overrides, dict) else {}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run declared stage smoke suites from Windmill.")
    parser.add_argument("--service", default="windmill")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--repo-path", default=None)
    parser.add_argument("--report-file", default="")
    parser.add_argument("--suite-ids", default="")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                service=args.service,
                environment=args.environment,
                repo_path=args.repo_path,
                report_file=args.report_file,
                suite_ids=args.suite_ids,
            ),
            indent=2,
            sort_keys=True,
        )
    )
