import os
import argparse
import json
import shlex
import subprocess
from pathlib import Path


def main(repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"), timeout_seconds: int = 60):
    repo_root = Path(repo_path)
    report_script = repo_root / "scripts" / "https_tls_assurance.py"
    if not report_script.exists():
        return {
            "status": "blocked",
            "reason": "https tls assurance script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        str(report_script),
        "--env",
        "production",
        "--timeout-seconds",
        str(timeout_seconds),
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
    parser = argparse.ArgumentParser(description="Run the ADR 0249 HTTPS/TLS assurance scan from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path, timeout_seconds=args.timeout_seconds), indent=2))
