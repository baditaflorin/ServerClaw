import json
import os
import shlex
import subprocess
from pathlib import Path


def main(
    image_id: str,
    repo_path: str = "/srv/proxmox_florin_server",
    tag: str = "",
    write: bool = False,
    apply: bool = False,
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "upgrade_container_image.py"

    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
            "image_id": image_id,
        }

    command = [str(workflow), "--image-id", image_id]
    if tag:
        command.extend(["--tag", tag])
    if write:
        command.append("--write")
    if apply:
        command.append("--apply")

    result = subprocess.run(command, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "image_id": image_id,
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
