import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path


REQUIRED_MODULE = "nats"


def missing_runtime_dependency() -> bool:
    return importlib.util.find_spec(REQUIRED_MODULE) is None


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    max_messages_per_subject: int = 10,
):
    repo_root = Path(repo_path)
    bridge_script = repo_root / "scripts" / "ntfy_nats_bridge.py"
    if not bridge_script.exists():
        return {
            "status": "blocked",
            "reason": "ntfy_nats_bridge.py is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "python3",
        str(bridge_script),
        "--repo-root",
        str(repo_root),
        "--max-messages-per-subject",
        str(max_messages_per_subject),
    ]
    if missing_runtime_dependency():
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            output_path = Path(handle.name)
        uv_command = [
            "uv",
            "run",
            "--with",
            "nats-py",
            "--with",
            "pyyaml",
            "python3",
            str(bridge_script),
            "--repo-root",
            str(repo_root),
            "--max-messages-per-subject",
            str(max_messages_per_subject),
        ]
        result = subprocess.run(
            uv_command,
            cwd=repo_root,
            env=dict(os.environ),
            text=True,
            capture_output=True,
            check=False,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        output_path.unlink(missing_ok=True)
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "command": " ".join(shlex.quote(part) for part in uv_command),
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    return {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the repo-managed ntfy NATS bridge from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--max-messages-per-subject", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path, max_messages_per_subject=args.max_messages_per_subject), indent=2))
