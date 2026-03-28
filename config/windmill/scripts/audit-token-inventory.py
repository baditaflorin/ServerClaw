import argparse
import json
import subprocess
from pathlib import Path


def _prepare_runtime_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o1777)
    return path


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    execute_remediations: bool = False,
    dry_run: bool = False,
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "token_lifecycle.py"
    receipt_dir = repo_root / "receipts" / "token-lifecycle"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "token lifecycle script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }
    try:
        receipt_dir = _prepare_runtime_directory(receipt_dir)
    except OSError as exc:
        return {
            "status": "blocked",
            "reason": "token lifecycle audit receipt directory is not writable",
            "receipt_dir": str(receipt_dir),
            "error": str(exc),
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
        "--receipt-dir",
        str(receipt_dir),
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
