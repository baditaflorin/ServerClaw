import argparse
import json
import subprocess
from pathlib import Path


def main(
    token_id: str = "",
    exposure_source: str = "",
    notes: str = "",
    repo_path: str = "/srv/proxmox_florin_server",
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
    if not token_id:
        return {"status": "blocked", "reason": "token_id is required"}

    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        str(workflow),
        "exposure-response",
        "--token-id",
        token_id,
        "--print-report-json",
    ]
    if exposure_source:
        command.extend(["--exposure-source", exposure_source])
    if notes:
        command.extend(["--notes", notes])
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
    parser = argparse.ArgumentParser(description="Run the ADR 0141 token exposure response workflow from Windmill.")
    parser.add_argument("--token-id", required=True)
    parser.add_argument("--exposure-source", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                token_id=args.token_id,
                exposure_source=args.exposure_source,
                notes=args.notes,
                repo_path=args.repo_path,
                dry_run=args.dry_run,
            ),
            indent=2,
        )
    )
