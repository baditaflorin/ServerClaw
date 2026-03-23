import json
import shlex
import subprocess
from pathlib import Path


def main(
    service: str,
    staging_receipt: str,
    repo_path: str = "/srv/proxmox_florin_server",
    branch: str = "",
    requester_class: str = "human_operator",
    approver_classes: str = "human_operator",
    extra_args: str = "",
    dry_run: bool = False,
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "promotion_pipeline.py"

    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
            "service": service,
        }

    command = [
        "python3",
        str(workflow),
        "--promote",
        "--service",
        service,
        "--staging-receipt",
        staging_receipt,
        "--requester-class",
        requester_class,
        "--approver-classes",
        approver_classes,
    ]
    if branch:
        command.extend(["--branch", branch])
    if extra_args:
        command.extend(["--extra-args", extra_args])
    if dry_run:
        command.append("--dry-run")

    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "service": service,
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
