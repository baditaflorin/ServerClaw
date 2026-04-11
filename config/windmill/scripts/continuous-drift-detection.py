import os
import json
import shlex
import subprocess
from pathlib import Path


def extract_report_json(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith("REPORT_JSON="):
            return json.loads(line.removeprefix("REPORT_JSON="))
    return None


def main(
    environment: str = "production",
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    publish_nats: bool = True,
):
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
            "environment": environment,
        }

    remote_command = [
        "cd",
        str(repo_root),
        "&&",
        "DRIFT_ENVIRONMENT=" + shlex.quote(environment),
        "uv",
        "run",
        "--with",
        "pyyaml",
        "--with",
        "dnspython",
        "--with",
        "nats-py",
        "python",
        "scripts/drift_detector.py",
        "--env",
        environment,
        "--print-report-json",
    ]
    if publish_nats:
        remote_command.append("--publish-nats")

    command = ["make", "remote-exec", "COMMAND=" + " ".join(remote_command)]
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    report = extract_report_json(result.stdout)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "environment": environment,
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if report is not None:
        payload["report"] = report
        payload["summary"] = report.get("summary", {})
    _publish_to_outline(payload, repo_root)
    return payload


def _publish_to_outline(payload: dict, repo_root: Path) -> None:
    import os, datetime

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
    import sys

    date = datetime.date.today().isoformat()
    environment = payload.get("environment", "production")
    title = f"drift-report-{environment}-{date}"
    status = payload.get("status", "unknown")
    icon = "✅" if status == "ok" else "❌"
    summary = payload.get("summary", {})
    md_lines = [
        f"# Drift Report: {environment} — {date}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Status | {icon} {status} |",
        f"| Environment | `{environment}` |",
    ]
    if isinstance(summary, dict):
        for k, v in summary.items():
            md_lines.append(f"| {k} | `{v}` |")
    report = payload.get("report", {})
    if isinstance(report, dict):
        events = report.get("events", [])
        if events:
            md_lines += ["", f"## Drift Events ({len(events)})", ""]
            for ev in events[:15]:
                if isinstance(ev, dict):
                    sev = ev.get("severity", "")
                    src = ev.get("source", "")
                    msg = ev.get("message") or ev.get("resource", "")
                    md_lines.append(f"- **[{sev}]** `{src}` — {msg}")
            if len(events) > 15:
                md_lines.append(f"- *({len(events) - 15} more events)*")
    md_lines.append("")
    content = "\n".join(md_lines)
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
                "--stdin",
            ],
            input=content,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass
