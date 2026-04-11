import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def main(repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server")):
    repo_root = Path(repo_path)
    roster_path = repo_root / "config" / "operators.yaml"
    if not roster_path.exists():
        return {
            "status": "blocked",
            "reason": "operator roster is missing from the worker checkout",
            "expected_roster_path": str(roster_path),
        }

    try:
        import yaml
    except ModuleNotFoundError:
        workflow = repo_root / "scripts" / "operator_manager.py"
        if not workflow.exists():
            return {
                "status": "blocked",
                "reason": "repo checkout not mounted on the worker",
                "expected_repo_path": str(repo_root),
            }
        command = ["uv", "run", "--no-project", "--with", "pyyaml", "python", str(workflow), "validate"]
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
        result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            return {
                "status": "error",
                "command": " ".join(shlex.quote(part) for part in command),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        payload = json.loads(result.stdout) if result.stdout.strip() else {}
    else:
        payload = yaml.safe_load(roster_path.read_text(encoding="utf-8")) or {}

    operators = payload.get("operators")
    if not isinstance(operators, list):
        return {"status": "error", "reason": "config/operators.yaml does not define an operators list"}

    items = []
    for operator in operators:
        if not isinstance(operator, dict):
            continue
        keycloak = operator.get("keycloak") if isinstance(operator.get("keycloak"), dict) else {}
        ssh = operator.get("ssh") if isinstance(operator.get("ssh"), dict) else {}
        tailscale = operator.get("tailscale") if isinstance(operator.get("tailscale"), dict) else {}
        audit = operator.get("audit") if isinstance(operator.get("audit"), dict) else {}
        public_keys = ssh.get("public_keys") if isinstance(ssh.get("public_keys"), list) else []
        items.append(
            {
                "id": operator.get("id", ""),
                "name": operator.get("name", ""),
                "email": operator.get("email", ""),
                "role": operator.get("role", ""),
                "status": operator.get("status", ""),
                "notes": operator.get("notes", ""),
                "keycloak_username": keycloak.get("username", ""),
                "realm_roles": keycloak.get("realm_roles", []) if isinstance(keycloak.get("realm_roles"), list) else [],
                "groups": keycloak.get("groups", []) if isinstance(keycloak.get("groups"), list) else [],
                "tailscale_login_email": tailscale.get("login_email", ""),
                "ssh_enabled": bool(public_keys),
                "onboarded_at": audit.get("onboarded_at", ""),
                "offboarded_at": audit.get("offboarded_at", ""),
                "last_reviewed_at": audit.get("last_reviewed_at", ""),
                "last_seen_at": audit.get("last_seen_at", ""),
            }
        )

    active = sum(1 for item in items if item["status"] == "active")
    inactive = sum(1 for item in items if item["status"] == "inactive")

    result = {
        "status": "ok",
        "operator_count": len(items),
        "active_count": active,
        "inactive_count": inactive,
        "operators": items,
    }
    _publish_roster_to_outline(result, repo_root)
    return result


def _publish_roster_to_outline(result: dict, repo_root: Path) -> None:
    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = repo_root / ".local" / "outline" / "api-token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return
    outline_tool = repo_root / "scripts" / "outline_tool.py"
    if not outline_tool.exists():
        return
    from datetime import datetime, timezone

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    operators = result.get("operators", [])
    lines = [
        f"# Operator Roster — {date}",
        "",
        f"**Total:** {result.get('operator_count', 0)}  "
        f"**Active:** {result.get('active_count', 0)}  "
        f"**Inactive:** {result.get('inactive_count', 0)}",
        "",
        "| ID | Name | Email | Role | Status | SSH | Onboarded |",
        "|---|---|---|---|---|---|---|",
    ]
    for op in operators:
        lines.append(
            f"| {op.get('id', '')} | {op.get('name', '')} | {op.get('email', '')} "
            f"| {op.get('role', '')} | {op.get('status', '')} "
            f"| {'yes' if op.get('ssh_enabled') else 'no'} | {op.get('onboarded_at', '')} |"
        )
    title = f"operator-roster-{date}"[:100]
    markdown = "\n".join(lines)
    try:
        subprocess.run(
            [
                sys.executable,
                str(outline_tool),
                "document.publish",
                "--collection",
                "Platform Findings",
                "--title",
                title,
            ],
            input=markdown,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass
