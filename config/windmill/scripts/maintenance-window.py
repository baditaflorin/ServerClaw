import json
import shlex
import subprocess
from pathlib import Path


def main(
    action: str = "open",
    service_id: str = "",
    reason: str = "",
    duration_minutes: int = 30,
    force: bool = False,
    repo_path: str = "/srv/proxmox_florin_server",
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "maintenance_window_tool.py"

    if action not in {"open", "close"}:
        return {
            "status": "blocked",
            "reason": "unsupported action",
            "action": action,
        }

    if not service_id:
        return {
            "status": "blocked",
            "reason": "service_id is required",
            "action": action,
        }

    if action == "open" and not reason:
        return {
            "status": "blocked",
            "reason": "reason is required for open",
            "action": action,
            "service_id": service_id,
        }

    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
            "action": action,
            "service_id": service_id,
        }

    command = ["python3", str(workflow), action, "--service", service_id]
    if action == "open":
        command.extend(["--reason", reason, "--duration-minutes", str(duration_minutes)])
    elif force:
        command.append("--force")

    result = subprocess.run(command, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "action": action,
        "service_id": service_id,
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
