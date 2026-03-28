import argparse
import json
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


LOCAL_FALLBACK_STAGES = [
    "generated-vars",
    "role-argument-specs",
    "json",
    "alert-rules",
    "generated-docs",
    "generated-portals",
]
LOCAL_PROVIDER_BOUNDARY_COMMAND = [
    "python3",
    "-m",
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
)


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _load_gate_status(status_path: Path) -> dict | None:
    if status_path.exists():
        return json.loads(status_path.read_text(encoding="utf-8"))
    return None


def _runner_image_pull_failed(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}"
    return any(marker in combined for marker in RUNNER_IMAGE_ERROR_MARKERS)


def _fallback_status_payload(
    *,
    repo_root: Path,
    manifest_path: Path,
    status: str,
    returncode: int,
    duration_seconds: float,
    commands: list[dict[str, object]],
) -> dict:
    return {
        "status": status,
        "source": "windmill-post-merge-local-fallback",
        "workspace": str(repo_root),
        "manifest": str(manifest_path),
        "executed_at": datetime.now(timezone.utc).isoformat(),
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


def _run_local_fallback(repo_root: Path, manifest_path: Path, status_path: Path) -> dict:
    commands = [
        ["./scripts/validate_repo.sh", *LOCAL_FALLBACK_STAGES],
        LOCAL_PROVIDER_BOUNDARY_COMMAND,
    ]
    started = time.monotonic()
    command_results: list[dict[str, object]] = []
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
    fallback_status = _fallback_status_payload(
        repo_root=repo_root,
        manifest_path=manifest_path,
        status="passed" if returncode == 0 else "failed",
        returncode=returncode,
        duration_seconds=duration_seconds,
        commands=command_results,
    )
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(fallback_status, indent=2) + "\n", encoding="utf-8")
    payload = {
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


def main(repo_path: str = "/srv/proxmox_florin_server"):
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
    result = _run(command, cwd=repo_root)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    gate_status = _load_gate_status(status_path)
    if gate_status is not None:
        payload["gate_status"] = gate_status
    if result.returncode != 0 and _runner_image_pull_failed(result.stdout, result.stderr):
        payload["primary_gate_error"] = {
            "command": payload["command"],
            "returncode": result.returncode,
            "stdout": payload["stdout"],
            "stderr": payload["stderr"],
        }
        return _run_local_fallback(repo_root, manifest_path, status_path) | {"primary_gate_error": payload["primary_gate_error"]}
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the repository validation gate after merge.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2))
