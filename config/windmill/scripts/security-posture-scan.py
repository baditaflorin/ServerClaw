import os
import argparse
import json
import shlex
import subprocess
from pathlib import Path


def main(repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server")):
    repo_root = Path(repo_path)
    report_script = repo_root / "scripts" / "security_posture_report.py"
    if not report_script.exists():
        return {
            "status": "blocked",
            "reason": "security posture report script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }
    required_paths = [
        repo_root / "inventory" / "host_vars" / "proxmox-host.yml",
        repo_root / "inventory" / "group_vars" / "all.yml",
        repo_root / "playbooks" / "tasks" / "security-scan.yml",
    ]
    missing_paths = [str(path) for path in required_paths if not path.exists()]
    if missing_paths:
        return {
            "status": "blocked",
            "reason": "security posture worker checkout is missing required repo paths",
            "missing_paths": missing_paths,
            "expected_repo_path": str(repo_root),
        }

    command = [
        "uv",
        "run",
        "--with",
        "ansible-core",
        "--with",
        "nats-py",
        "--with",
        "pyyaml",
        "python",
        str(report_script),
        "--env",
        "production",
        "--audit-surface",
        "windmill",
        "--publish-nats",
        "--print-report-json",
    ]
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    has_report_json = "REPORT_JSON=" in stdout
    return {
        "status": "ok" if result.returncode in {0, 1, 2} and has_report_json else "error",
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ADR 0102 security posture workflow from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2))
