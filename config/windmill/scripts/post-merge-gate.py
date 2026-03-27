import argparse
import json
import shlex
import subprocess
from pathlib import Path


def main(repo_path: str = "/srv/proxmox_florin_server"):
    repo_root = Path(repo_path)
    gate_script = repo_root / "scripts" / "run_gate.py"
    manifest_path = repo_root / "config" / "validation-gate.json"
    status_path = repo_root / ".local" / "validation-gate" / "post-merge-last-run.json"

    if not gate_script.exists() or not manifest_path.exists():
        return {
            "status": "blocked",
            "reason": "validation gate surfaces are missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "python3",
        str(gate_script),
        "--manifest",
        str(manifest_path),
        "--workspace",
        str(repo_root),
        "--status-file",
        str(status_path),
        "--source",
        "windmill-post-merge",
        "--print-json",
    ]
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if status_path.exists():
        payload["gate_status"] = json.loads(status_path.read_text(encoding="utf-8"))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the repository validation gate after merge.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2))
