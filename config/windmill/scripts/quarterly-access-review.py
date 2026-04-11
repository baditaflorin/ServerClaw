import json
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RUNTIME_ENV_FILE = Path("/run/lv3-secrets/windmill/runtime.env")
RUNTIME_ENV_KEYS = {
    "LV3_OPENBAO_URL",
    "KEYCLOAK_BOOTSTRAP_PASSWORD",
    "OPENBAO_INIT_JSON",
    "TAILSCALE_API_KEY",
    "TAILSCALE_TAILNET",
    "LV3_TAILSCALE_INVITE_ENDPOINT",
    "LV3_STEP_CA_SSH_REGISTER_COMMAND",
    "LV3_STEP_CA_SSH_REVOKE_COMMAND",
    "LV3_MATTERMOST_WEBHOOK",
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
    env.setdefault("LV3_OPENBAO_URL", "http://lv3-openbao:8201")
    return env


def _is_first_monday_of_quarter(now: datetime | None = None) -> bool:
    candidate = now or datetime.now(ZoneInfo("Europe/Bucharest"))
    return candidate.month in (1, 4, 7, 10) and candidate.weekday() == 0 and 1 <= candidate.day <= 7


def main(
    warning_days: int = 45,
    inactive_days: int = 60,
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    schedule_guard: str = "",
    dry_run: bool = False,
):
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "operator_manager.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }
    if schedule_guard == "first_monday_of_quarter" and not _is_first_monday_of_quarter():
        return {
            "status": "skipped",
            "reason": "quarterly access review only runs on the first Monday of each quarter",
            "schedule_guard": schedule_guard,
        }

    command = [
        "uvx",
        "--from",
        "pyyaml",
        "python",
        str(workflow),
        "--emit-json",
        "quarterly-review",
        "--warning-days",
        str(warning_days),
        "--inactive-days",
        str(inactive_days),
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
