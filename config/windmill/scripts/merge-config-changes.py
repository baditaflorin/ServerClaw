from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def main(
    repo_path: str = "/srv/proxmox_florin_server",
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

    resolved_dsn = (dsn or os.environ.get("LV3_CONFIG_MERGE_DSN") or os.environ.get("DATABASE_URL") or "").strip()
    if not resolved_dsn:
        return {
            "status": "blocked",
            "reason": "LV3_CONFIG_MERGE_DSN or DATABASE_URL is required for config merges",
            "expected_repo_path": str(repo_root),
        }

    command = [
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
    if publish_nats:
        command.append("--publish-nats")
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
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--dsn")
    parser.add_argument("--publish-nats", action="store_true")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path, dsn=args.dsn, publish_nats=args.publish_nats), indent=2))
