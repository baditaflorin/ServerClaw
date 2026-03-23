import json
import shlex
import subprocess
from pathlib import Path


def extract_report_json(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith("REPORT_JSON="):
            return json.loads(line.removeprefix("REPORT_JSON="))
    return None


def main(
    environment: str = "production",
    repo_path: str = "/srv/proxmox_florin_server",
    publish_nats: bool = True,
):
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
            "environment": environment,
        }

    remote_command = [
        "cd",
        str(repo_root),
        "&&",
        "DRIFT_ENVIRONMENT=" + shlex.quote(environment),
        "uv",
        "run",
        "--with",
        "pyyaml",
        "--with",
        "dnspython",
        "--with",
        "nats-py",
        "python",
        "scripts/drift_detector.py",
        "--env",
        environment,
        "--print-report-json",
    ]
    if publish_nats:
        remote_command.append("--publish-nats")

    command = ["make", "remote-exec", "COMMAND=" + " ".join(remote_command)]
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    report = extract_report_json(result.stdout)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "environment": environment,
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if report is not None:
        payload["report"] = report
        payload["summary"] = report.get("summary", {})
    return payload
