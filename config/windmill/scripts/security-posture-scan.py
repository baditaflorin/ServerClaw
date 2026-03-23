import argparse
import json
import subprocess
from pathlib import Path


def main(repo_path: str = "/srv/proxmox_florin_server"):
    repo_root = Path(repo_path)
    report_script = repo_root / "scripts" / "security_posture_report.py"
    if not report_script.exists():
        return {
            "status": "blocked",
            "reason": "security posture report script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "python3",
        str(report_script),
        "--env",
        "production",
        "--audit-surface",
        "windmill",
        "--publish-nats",
        "--print-report-json",
    ]
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    return {
        "status": "ok" if result.returncode in {0, 2} else "error",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ADR 0102 security posture workflow from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2))
