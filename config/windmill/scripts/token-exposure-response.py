import os
import argparse
import json
import subprocess
from pathlib import Path


def _prepare_runtime_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if (path.stat().st_mode & 0o7777) != 0o1777:
        try:
            path.chmod(0o1777)
        except OSError:
            pass
    probe = path / ".windmill-write-probe"
    probe.write_text("", encoding="utf-8")
    probe.unlink()
    return path


def main(
    token_id: str = "",
    exposure_source: str = "",
    notes: str = "",
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    dry_run: bool = False,
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "token_lifecycle.py"
    incident_dir = repo_root / ".local" / "token-lifecycle" / "incidents"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "token lifecycle script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }
    if not token_id:
        return {"status": "blocked", "reason": "token_id is required"}
    try:
        incident_dir = _prepare_runtime_directory(incident_dir)
    except OSError as exc:
        return {
            "status": "blocked",
            "reason": "token exposure incident directory is not writable",
            "incident_dir": str(incident_dir),
            "error": str(exc),
        }

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
        "--incident-dir",
        str(incident_dir),
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
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
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
