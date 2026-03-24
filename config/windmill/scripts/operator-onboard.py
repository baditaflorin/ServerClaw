import json
import os
import shlex
import subprocess
from pathlib import Path


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
        "--with",
        "pyyaml",
        "python",
        str(workflow),
        "onboard",
        "--name",
        name,
        "--email",
        email,
        "--role",
        role,
        "--emit-json",
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

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
    result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
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
