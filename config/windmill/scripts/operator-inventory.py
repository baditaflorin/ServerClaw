import json
import os
import shlex
import subprocess
from pathlib import Path


def main(
    operator_id: str = "",
    repo_path: str = "/srv/proxmox_florin_server",
    offline: bool = False,
    dry_run: bool = False,
):
    if not operator_id:
        return {"status": "blocked", "reason": "operator_id is required"}

    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "operator_access_inventory.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        str(workflow),
        "--id",
        operator_id,
        "--format",
        "json",
    ]
    if offline:
        command.append("--offline")
    if dry_run:
        command.append("--dry-run")

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
    result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(shlex.quote(part) for part in command),
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
