#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    scenario: str = "load",
    service: str = "",
    publish_nats: bool = False,
    notify_ntfy: bool = False,
    runner_context: str = "windmill",
    environment: str = "production",
    soak_duration: str = "",
) -> dict[str, object]:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "k6_load_testing.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": f"missing k6 runner at {script_path}",
        }

    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "--with",
        "nats-py",
        "python",
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--scenario",
        scenario,
        "--runner-context",
        runner_context,
        "--environment",
        environment,
    ]
    if service.strip():
        command.extend(["--service", service.strip()])
    if publish_nats:
        command.append("--publish-nats")
    if notify_ntfy:
        command.append("--notify-ntfy")
    if soak_duration.strip():
        command.extend(["--soak-duration", soak_duration.strip()])

    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "status": "error",
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    payload = json.loads(completed.stdout)
    payload["status"] = "ok"
    payload["command"] = command
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the repo-managed k6 wrapper from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--scenario", choices=["smoke", "load", "soak"], default="load")
    parser.add_argument("--service", default="")
    parser.add_argument("--publish-nats", action="store_true")
    parser.add_argument("--notify-ntfy", action="store_true")
    parser.add_argument("--runner-context", default="windmill")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--soak-duration", default="")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                scenario=args.scenario,
                service=args.service,
                publish_nats=args.publish_nats,
                notify_ntfy=args.notify_ntfy,
                runner_context=args.runner_context,
                environment=args.environment,
                soak_duration=args.soak_duration,
            ),
            indent=2,
        )
    )
