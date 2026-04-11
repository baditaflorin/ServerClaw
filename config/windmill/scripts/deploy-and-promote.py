import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.logging import get_logger, set_context


LOGGER = get_logger("windmill", "deploy_and_promote", name="lv3.windmill.deploy_and_promote")


def main(
    service: str,
    staging_receipt: str,
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    branch: str = "",
    requester_class: str = "human_operator",
    approver_classes: str = "human_operator",
    extra_args: str = "",
    dry_run: bool = False,
    trace_id: str = "",
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "promotion_pipeline.py"
    effective_trace_id = trace_id.strip() or os.environ.get("PLATFORM_TRACE_ID", "").strip() or "background"
    set_context(trace_id=effective_trace_id, workflow_id="deploy-and-promote", target=f"service:{service}")

    if not workflow.exists():
        LOGGER.error("Promotion pipeline missing from worker checkout", extra={"error_code": "WORKFLOW_MISSING"})
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

    env = dict(os.environ)
    env["PLATFORM_TRACE_ID"] = effective_trace_id
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False, env=env)
    LOGGER.info(
        "Executed promotion pipeline",
        extra={
            "target": f"service:{service}",
            "status_code": result.returncode,
            "duration_ms": None,
        },
    )
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "service": service,
        "trace_id": effective_trace_id,
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
