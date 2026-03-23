import json
import shlex
import subprocess
from pathlib import Path


def main(
    operator_id: str = "",
    repo_path: str = "/srv/proxmox_florin_server",
    dry_run: bool = False,
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "operator_manager.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    command = ["uvx", "--from", "pyyaml", "python", str(workflow), "sync", "--emit-json"]
    if operator_id:
        command.extend(["--id", operator_id])
    if dry_run:
        command.append("--dry-run")

    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
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
