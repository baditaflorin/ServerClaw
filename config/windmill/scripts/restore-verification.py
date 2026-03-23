import json
import subprocess
from pathlib import Path


def extract_report_json(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith("REPORT_JSON="):
            return json.loads(line.removeprefix("REPORT_JSON="))
    return None


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    publish_nats: bool = True,
    triggered_by: str = "windmill-schedule",
):
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "restore_verification.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "restore verification surfaces are missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
    ]
    if publish_nats:
        command.extend(["--with", "nats-py"])
    command.extend(
        [
            "python",
            str(script_path),
            "--triggered-by",
            triggered_by,
            "--print-report-json",
        ]
    )
    if publish_nats:
        command.append("--publish-nats")

    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    report = extract_report_json(result.stdout)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if report is not None:
        payload["report"] = report
        payload["summary"] = report.get("summary", {})
    return payload


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
