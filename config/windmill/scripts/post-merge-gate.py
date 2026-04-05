import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict


GIT_REQUIRED_FALLBACK_STAGES = [
    "workstream-surfaces",
    "agent-standards",
]
WORKER_SAFE_FALLBACK_STAGES = [
    "generated-vars",
    "role-argument-specs",
    "json",
    "alert-rules",
    "generated-docs",
    "generated-portals",
]
LOCAL_PROVIDER_BOUNDARY_COMMAND = [
    "uv",
    "run",
    "--with",
    "pyyaml",
    "python3",
    "scripts/provider_boundary_catalog.py",
    "--validate",
]
RUNNER_IMAGE_ERROR_MARKERS = (
    "unsupported manifest media type",
    "Unable to find image 'registry.lv3.org/check-runner/",
    "docker: error during connect:",
    "Cannot connect to the Docker daemon",
    "docker.sock/_ping",
)
VALIDATION_RUNNER_ID = "windmill-post-merge-worker"


class CommandResult(TypedDict):
    command: str
    returncode: int


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _load_gate_status(status_path: Path) -> dict[str, Any] | None:
    if status_path.exists():
        return json.loads(status_path.read_text(encoding="utf-8"))
    return None


def _git_checkout_available(repo_root: Path) -> bool:
    result = _run(["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"], cwd=repo_root)
    return result.returncode == 0 and result.stdout.strip() == "true"


def _runner_image_pull_failed(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}"
    return any(marker in combined for marker in RUNNER_IMAGE_ERROR_MARKERS)


def _gate_status_runner_startup_failed(gate_status: dict[str, Any] | None) -> bool:
    if not gate_status or gate_status.get("status") == "passed":
        return False
    checks = gate_status.get("checks")
    if not isinstance(checks, list):
        return False
    return any(isinstance(check, dict) and check.get("returncode") == 125 for check in checks)


def _load_runner_context(repo_root: Path) -> dict[str, Any]:
    command = [
        sys.executable or "python3",
        str(repo_root / "scripts" / "validation_runner_contracts.py"),
        "--runner",
        VALIDATION_RUNNER_ID,
        "--workspace",
        str(repo_root),
        "--format",
        "json",
    ]
    result = _run(command, cwd=repo_root)
    if result.returncode != 0:
        return {
            "id": VALIDATION_RUNNER_ID,
            "load_error": result.stderr.strip()
            or result.stdout.strip()
            or f"command exited {result.returncode}",
        }
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "id": VALIDATION_RUNNER_ID,
            "load_error": result.stdout.strip() or "runner context did not return JSON",
        }


def _fallback_status_payload(
    *,
    repo_root: Path,
    manifest_path: Path,
    status: str,
    returncode: int,
    duration_seconds: float,
    commands: list[CommandResult],
    runner_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "source": "windmill-post-merge-local-fallback",
        "workspace": str(repo_root),
        "manifest": str(manifest_path),
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "runner": runner_context,
        "checks": [
            {
                "id": "local-fallback",
                "severity": "error",
                "description": "Run the worker-local validate_repo fallback when runner images are unavailable on the worker host.",
                "status": status,
                "returncode": returncode,
                "duration_seconds": round(duration_seconds, 2),
                "docker_command": [],
                "commands": commands,
            }
        ],
        "requested_checks": ["local-fallback"],
    }


def _run_local_fallback(repo_root: Path, manifest_path: Path, status_path: Path) -> dict[str, Any]:
    fallback_stages = list(WORKER_SAFE_FALLBACK_STAGES)
    if _git_checkout_available(repo_root):
        fallback_stages = [*GIT_REQUIRED_FALLBACK_STAGES, *fallback_stages]
    commands = [
        ["./scripts/validate_repo.sh", *fallback_stages],
        LOCAL_PROVIDER_BOUNDARY_COMMAND,
    ]
    started = time.monotonic()
    command_results: list[CommandResult] = []
    combined_stdout: list[str] = []
    combined_stderr: list[str] = []
    returncode = 0

    for command in commands:
        result = _run(command, cwd=repo_root)
        rendered_command = " ".join(shlex.quote(part) for part in command)
        command_results.append(
            {
                "command": rendered_command,
                "returncode": result.returncode,
            }
        )
        if result.stdout.strip():
            combined_stdout.append(f"$ {rendered_command}\n{result.stdout.strip()}")
        if result.stderr.strip():
            combined_stderr.append(f"$ {rendered_command}\n{result.stderr.strip()}")
        if result.returncode != 0:
            returncode = result.returncode
            break

    duration_seconds = time.monotonic() - started
    runner_context = _load_runner_context(repo_root)
    fallback_status = _fallback_status_payload(
        repo_root=repo_root,
        manifest_path=manifest_path,
        status="passed" if returncode == 0 else "failed",
        returncode=returncode,
        duration_seconds=duration_seconds,
        commands=command_results,
        runner_context=runner_context,
    )
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(fallback_status, indent=2) + "\n", encoding="utf-8")
    payload: dict[str, Any] = {
        "status": "ok" if returncode == 0 else "error",
        "command": " && ".join(entry["command"] for entry in command_results),
        "commands": command_results,
        "returncode": returncode,
        "stdout": "\n\n".join(combined_stdout).strip(),
        "stderr": "\n\n".join(combined_stderr).strip(),
        "fallback_used": True,
        "gate_status": fallback_status,
    }
    return payload


def _publish_to_outline(repo_root: Path, payload: dict[str, Any]) -> None:
    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        return
    outline_tool = repo_root / "scripts" / "outline_tool.py"
    if not outline_tool.exists():
        return
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"post-merge-gate-{date}"
    status = payload.get("status", "unknown")
    gate_status = payload.get("gate_status", {})
    checks = gate_status.get("checks", []) if isinstance(gate_status, dict) else []
    lane_rows = ""
    for check in checks:
        if isinstance(check, dict):
            icon = "✅" if check.get("status") == "passed" else "❌"
            lane_rows += f"| {check.get('id', '?')} | {icon} {check.get('status', '?')} |\n"
    md_lines = [
        f"# Post-Merge Gate: {date}\n",
        f"| Field | Value |\n|---|---|\n",
        f"| Status | {status} |\n",
        f"| Source | windmill-post-merge |\n",
        f"| Run date | {datetime.now(timezone.utc).isoformat()} |\n\n",
    ]
    if lane_rows:
        md_lines.append("## Gate Checks\n\n| Lane | Result |\n|---|---|\n")
        md_lines.append(lane_rows + "\n")
    md_content = "".join(md_lines)
    try:
        subprocess.run(
            [sys.executable, str(outline_tool), "document.publish",
             "--collection", "Automation Runs", "--title", title, "--stdin"],
            input=md_content,
            text=True,
            capture_output=True,
            check=False,
            cwd=repo_root,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict[str, Any]:
    repo_root = Path(repo_path)
    gate_script = repo_root / "scripts" / "run_gate.py"
    manifest_path = repo_root / "config" / "validation-gate.json"
    status_path = repo_root / ".local" / "validation-gate" / "post-merge-last-run.json"

    if not gate_script.exists() or not manifest_path.exists():
        return {
            "status": "blocked",
            "reason": "validation gate surfaces are missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "python3",
        str(gate_script),
        "--manifest",
        str(manifest_path),
        "--workspace",
        str(repo_root),
        "--status-file",
        str(status_path),
        "--source",
        "windmill-post-merge",
        "--print-json",
    ]
    previous_runner_id = os.environ.get("LV3_VALIDATION_RUNNER_ID")
    os.environ["LV3_VALIDATION_RUNNER_ID"] = VALIDATION_RUNNER_ID
    try:
        result = _run(command, cwd=repo_root)
    finally:
        if previous_runner_id is None:
            os.environ.pop("LV3_VALIDATION_RUNNER_ID", None)
        else:
            os.environ["LV3_VALIDATION_RUNNER_ID"] = previous_runner_id
    gate_status = _load_gate_status(status_path)
    payload: dict[str, Any] = {
        "status": "ok"
        if result.returncode == 0 and (gate_status is None or gate_status.get("status") == "passed")
        else "error",
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if gate_status is not None:
        payload["gate_status"] = gate_status
    runner_startup_failed = _runner_image_pull_failed(result.stdout, result.stderr) or _gate_status_runner_startup_failed(
        gate_status
    )
    if payload["status"] == "error" and runner_startup_failed:
        payload["primary_gate_error"] = {
            "command": payload["command"],
            "returncode": result.returncode,
            "stdout": payload["stdout"],
            "stderr": payload["stderr"],
        }
        result_payload = _run_local_fallback(repo_root, manifest_path, status_path) | {"primary_gate_error": payload["primary_gate_error"]}
        _publish_to_outline(repo_root, result_payload)
        return result_payload
    _publish_to_outline(repo_root, payload)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the repository validation gate after merge.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2))
