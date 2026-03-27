import json
import os
import shlex
import subprocess
from pathlib import Path

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


def main(
    name: str = "",
    email: str = "",
    role: str = "operator",
    ssh_key: str = "",
    operator_id: str = "",
    keycloak_username: str = "",
    tailscale_login_email: str = "",
    tailscale_device_name: str = "",
    bootstrap_password: str = "",
    repo_path: str = "/srv/proxmox_florin_server",
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

    missing = [field for field, value in {"name": name, "email": email, "role": role}.items() if not value]
    if role in {"admin", "operator"} and not ssh_key:
        missing.append("ssh_key")
    if missing:
        return {"status": "blocked", "reason": f"missing required inputs: {', '.join(sorted(missing))}"}

    command = [
        "uv",
        "run",
        "--no-project",
        "--with",
        "pyyaml",
        "python",
        str(workflow),
        "--emit-json",
        "onboard",
        "--name",
        name,
        "--email",
        email,
        "--role",
        role,
    ]
    if ssh_key:
        command.extend(["--ssh-key", ssh_key])
    if operator_id:
        command.extend(["--id", operator_id])
    if keycloak_username:
        command.extend(["--keycloak-username", keycloak_username])
    if tailscale_login_email:
        command.extend(["--tailscale-login-email", tailscale_login_email])
    if tailscale_device_name:
        command.extend(["--tailscale-device-name", tailscale_device_name])
    if bootstrap_password:
        command.extend(["--bootstrap-password", bootstrap_password])
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
