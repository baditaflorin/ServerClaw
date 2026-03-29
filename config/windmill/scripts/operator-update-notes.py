import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

RUNTIME_ENV_FILE = Path("/run/lv3-secrets/windmill/runtime.env")
RUNTIME_ENV_KEYS = {
    "LV3_OPERATOR_MANAGER_SURFACE",
}


def build_subprocess_env(repo_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
    if RUNTIME_ENV_FILE.exists():
        for line in RUNTIME_ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in RUNTIME_ENV_KEYS:
                env[key] = value
    env.setdefault("LV3_OPERATOR_MANAGER_SURFACE", "windmill")
    return env


def main(
    operator_id: str = "",
    notes_markdown: str = "",
    repo_path: str = "/srv/proxmox_florin_server",
    dry_run: bool = False,
):
    if not operator_id:
        return {"status": "blocked", "reason": "operator_id is required"}

    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "operator_manager.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    temp_path: Path | None = None
    command: list[str] = []
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(notes_markdown)
            temp_path = Path(handle.name)

        command = [
            "uv",
            "run",
            "--no-project",
            "--with",
            "pyyaml",
            "python",
            str(workflow),
            "--emit-json",
            "update-notes",
            "--id",
            operator_id,
            "--notes-file",
            str(temp_path),
        ]
        if dry_run:
            command.append("--dry-run")

        result = subprocess.run(
            command,
            cwd=repo_root,
            env=build_subprocess_env(repo_root),
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()

    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(shlex.quote(part) for part in command),
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
