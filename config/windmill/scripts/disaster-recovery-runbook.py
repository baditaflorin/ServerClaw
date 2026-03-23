import json
import shlex
import subprocess
from pathlib import Path


def main(
    tier: str = "all",
    repo_path: str = "/srv/proxmox_florin_server",
    format: str = "json",
    dry_run: bool = False,
):
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "disaster_recovery_runbook.py"

    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    command = ["python3", str(script_path), "--tier", tier, "--format", format]
    if dry_run:
        return {
            "status": "ok",
            "dry_run": True,
            "command": " ".join(shlex.quote(part) for part in command),
        }

    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if format == "json" and result.stdout.strip():
        try:
            payload["result"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return payload
