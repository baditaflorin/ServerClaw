import argparse
import json
import subprocess
from pathlib import Path


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    execute_remediations: bool = False,
    dry_run: bool = False,
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "token_lifecycle.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "token lifecycle script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        str(workflow),
        "audit",
        "--print-report-json",
    ]
    if execute_remediations:
        command.append("--execute-remediations")
    if dry_run:
        command.append("--dry-run")
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode in {0, 2} else "error",
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ADR 0141 token inventory audit from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--execute-remediations", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                execute_remediations=args.execute_remediations,
                dry_run=args.dry_run,
            ),
            indent=2,
        )
    )
