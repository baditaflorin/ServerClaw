from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


CONFIG_MERGE_RUNTIME_DEPENDENCIES = ("pyyaml", "psycopg[binary]")


def resolve_dsn(explicit_dsn: str | None = None, proc_environ_path: str = "/proc/1/environ") -> str:
    direct = (explicit_dsn or os.environ.get("LV3_CONFIG_MERGE_DSN") or os.environ.get("DATABASE_URL") or "").strip()
    if direct:
        return direct

    proc_environ = Path(proc_environ_path)
    if not proc_environ.exists():
        return ""

    try:
        entries = proc_environ.read_bytes().split(b"\0")
    except OSError:
        return ""

    for entry in entries:
        if entry.startswith(b"LV3_CONFIG_MERGE_DSN="):
            return entry.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
        if entry.startswith(b"DATABASE_URL="):
            return entry.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
    return ""


def build_command(workflow: Path, repo_root: Path, resolved_dsn: str, publish_nats: bool = False) -> list[str]:
    command = ["uv", "run"]
    for dependency in CONFIG_MERGE_RUNTIME_DEPENDENCIES:
        command.extend(["--with", dependency])
    command.extend(
        [
            "python3",
            str(workflow),
            "--repo-root",
            str(repo_root),
            "merge",
            "--dsn",
            resolved_dsn,
            "--actor",
            "agent/config-merge-job",
        ]
    )
    if publish_nats:
        command.append("--publish-nats")
    return command


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    dsn: str | None = None,
    publish_nats: bool = False,
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "config_merge_protocol.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "config merge protocol script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    resolved_dsn = resolve_dsn(dsn)
    if not resolved_dsn:
        return {
            "status": "blocked",
            "reason": "LV3_CONFIG_MERGE_DSN or DATABASE_URL is required for config merges",
            "expected_repo_path": str(repo_root),
        }

    command = build_command(workflow, repo_root, resolved_dsn, publish_nats=publish_nats)
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the ADR 0158 config-merge workflow from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--dsn")
    parser.add_argument("--publish-nats", action="store_true")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path, dsn=args.dsn, publish_nats=args.publish_nats), indent=2))
