#!/usr/bin/env python3
"""Windmill wrapper for the repo-managed Atlas drift check."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

JOB_SECRET_ROOT = Path(".local") / "windmill-job-secrets"
DEFAULT_ATLAS_DRIFT_OPERATION_TIMEOUT_SECONDS = 8
DEFAULT_ATLAS_DRIFT_RUNTIME_TIMEOUT_SECONDS = 170


def positive_int_env(name: str, default: int) -> int:
    """Read a positive bounded runtime override without widening the job."""

    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    # An environment override may tighten the budget, never lengthen the
    # worker's fixed operational ceiling.
    return min(value, default) if value > 0 else default


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
        if (resolved / "scripts" / "atlas_schema.py").is_file() and (
            resolved / "scripts" / "run_python_with_packages.sh"
        ).is_file():
            return resolved
    return Path("/srv/platform_server")


def set_default_env(env: dict[str, str], name: str, value: str) -> None:
    if not env.get(name, "").strip():
        env[name] = value


def set_default_env_from_text_file(env: dict[str, str], name: str, path: Path) -> None:
    if env.get(name, "").strip():
        return
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if value:
        env[name] = value


def set_default_env_from_json_file(env: dict[str, str], name: str, path: Path) -> None:
    if env.get(name, "").strip():
        return
    try:
        raw_value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if not raw_value:
        return
    try:
        env[name] = json.dumps(json.loads(raw_value))
    except json.JSONDecodeError:
        env[name] = raw_value


def read_proc_env_var(name: str, proc_environ_path: Path = Path("/proc/1/environ")) -> str:
    if not proc_environ_path.exists():
        return ""
    try:
        entries = proc_environ_path.read_bytes().split(b"\0")
    except OSError:
        return ""
    prefix = f"{name}=".encode("utf-8")
    for entry in entries:
        if entry.startswith(prefix):
            return entry.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
    return ""


def set_default_env_from_proc_env(env: dict[str, str], name: str) -> None:
    if env.get(name, "").strip():
        return
    value = read_proc_env_var(name)
    if value:
        env[name] = value


def set_default_env_from_json_paths(env: dict[str, str], name: str, paths: tuple[Path, ...]) -> None:
    for path in paths:
        set_default_env_from_json_file(env, name, path)
        if env.get(name, "").strip():
            return


def set_default_env_from_text_paths(env: dict[str, str], name: str, paths: tuple[Path, ...]) -> None:
    for path in paths:
        set_default_env_from_text_file(env, name, path)
        if env.get(name, "").strip():
            return


def main(
    repo_path: str | None = None,
    publish_nats: bool = True,
    publish_ntfy: bool = True,
    write_receipts: bool = True,
) -> dict[str, object]:
    repo_root = _resolve_repo_root(repo_path)
    atlas_script = repo_root / "scripts" / "atlas_schema.py"
    package_runner = repo_root / "scripts" / "run_python_with_packages.sh"
    if not atlas_script.exists() or not package_runner.exists():
        return {
            "status": "blocked",
            "reason": "Atlas drift surfaces are missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        str(package_runner),
        "docker",
        "nats-py",
        "psycopg[binary]",
        "pyyaml",
        "--",
        "scripts/atlas_schema.py",
        "drift",
        "--repo-root",
        str(repo_root),
        "--format",
        "json",
    ]
    if write_receipts:
        command.append("--write-receipts")
    if publish_nats:
        command.append("--publish-nats")
    if publish_ntfy:
        command.append("--publish-ntfy")

    command_env = os.environ.copy()
    # Windmill workers run on the private runtime guest and can talk to Atlas dependencies directly.
    set_default_env(command_env, "LV3_ATLAS_FORCE_DIRECT_ENDPOINTS", "1")
    set_default_env(command_env, "LV3_NATS_URL", "nats://127.0.0.1:4222")
    set_default_env(
        command_env,
        "LV3_ATLAS_OPERATION_TIMEOUT_SECONDS",
        str(DEFAULT_ATLAS_DRIFT_OPERATION_TIMEOUT_SECONDS),
    )
    set_default_env_from_json_paths(
        command_env,
        "LV3_ATLAS_OPENBAO_APPROLE_JSON",
        (
            repo_root / JOB_SECRET_ROOT / "openbao" / "atlas-approle.json",
            repo_root / ".local" / "openbao" / "atlas-approle.json",
        ),
    )
    set_default_env_from_proc_env(command_env, "LV3_ATLAS_OPENBAO_APPROLE_JSON")
    set_default_env_from_json_paths(
        command_env,
        "LV3_ATLAS_OPENBAO_INIT_JSON",
        (
            repo_root / JOB_SECRET_ROOT / "openbao" / "init.json",
            repo_root / ".local" / "openbao" / "init.json",
        ),
    )
    set_default_env_from_proc_env(command_env, "LV3_ATLAS_OPENBAO_INIT_JSON")
    set_default_env_from_text_paths(
        command_env,
        "LV3_NTFY_ALERTMANAGER_PASSWORD",
        (
            repo_root / JOB_SECRET_ROOT / "ntfy" / "alertmanager-password.txt",
            repo_root / ".local" / "ntfy" / "alertmanager-password.txt",
        ),
    )
    set_default_env_from_proc_env(command_env, "LV3_NTFY_ALERTMANAGER_PASSWORD")
    runtime_timeout_seconds = positive_int_env(
        "LV3_WINDMILL_ATLAS_DRIFT_TIMEOUT_SECONDS",
        DEFAULT_ATLAS_DRIFT_RUNTIME_TIMEOUT_SECONDS,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            env=command_env,
            timeout=runtime_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        timeout_payload: dict[str, object] = {
            "status": "timeout",
            "returncode": 124,
            "reason": (
                f"Atlas drift command exceeded its bounded Windmill runtime of {runtime_timeout_seconds} seconds"
            ),
        }
        _publish_drift_to_outline(timeout_payload, repo_root)
        return timeout_payload
    payload: dict[str, object] = {
        "status": "ok" if completed.returncode == 0 else "error",
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    if completed.stdout.strip():
        try:
            payload["report"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload["status"] = "error"
            payload["reason"] = "Atlas drift command did not return valid JSON"
    report = payload.get("report")
    if completed.returncode == 2 and isinstance(report, dict):
        report_status = str(report.get("status") or "").strip().lower()
        if report_status == "drift_detected":
            payload["status"] = "drift"
        elif report_status == "clean":
            payload["status"] = "ok"
    _publish_drift_to_outline(payload, repo_root)
    return payload


def _publish_drift_to_outline(payload: dict, repo_root: Path) -> None:
    import sys as _sys

    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = repo_root / ".local" / "outline" / "api-token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return
    outline_tool = repo_root / "scripts" / "outline_tool.py"
    if not outline_tool.exists():
        return
    from datetime import datetime, timezone

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = payload.get("status", "unknown")
    report = payload.get("report") or {}
    drift_items = report.get("drift", []) if isinstance(report.get("drift"), list) else []
    lines = [
        f"# Atlas Drift Check — {date}",
        "",
        f"**Status:** {status}",
        "",
    ]
    if drift_items:
        lines += ["## Drift Items", "", "| Resource | Expected | Actual |", "|---|---|---|"]
        for item in drift_items[:20]:
            res = str(item.get("resource", "")).replace("|", "\\|")
            exp = str(item.get("expected", "")).replace("|", "\\|")
            act = str(item.get("actual", "")).replace("|", "\\|")
            lines.append(f"| {res} | {exp} | {act} |")
        lines.append("")
    title = f"atlas-drift-{date}"[:100]
    markdown = "\n".join(lines)
    try:
        proc = subprocess.run(
            [
                _sys.executable,
                str(outline_tool),
                "document.publish",
                "--collection",
                "Platform Findings",
                "--title",
                title,
            ],
            input=markdown,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
        _ = proc
    except OSError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the repo-managed Atlas drift check from Windmill.")
    parser.add_argument("--repo-path", default=None)
    parser.add_argument("--no-publish-nats", action="store_true")
    parser.add_argument("--no-publish-ntfy", action="store_true")
    parser.add_argument("--no-write-receipts", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                publish_nats=not args.no_publish_nats,
                publish_ntfy=not args.no_publish_ntfy,
                write_receipts=not args.no_write_receipts,
            ),
            indent=2,
            sort_keys=True,
        )
    )
