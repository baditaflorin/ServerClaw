import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main(repo_path: str = "/srv/proxmox_florin_server"):
    repo_root = Path(repo_path)
    report_script = repo_root / "scripts" / "public_surface_scan.py"
    if not report_script.exists():
        return {
            "status": "blocked",
            "reason": "public surface scan script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "python3",
        str(report_script),
        "--env",
        "production",
        "--publish-nats",
        "--print-report-json",
    ]
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    payload = {
        "status": "ok" if result.returncode in {0, 1, 2} else "error",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    _publish_to_outline(payload, repo_root)
    return payload


def _publish_to_outline(payload: dict, repo_root: Path) -> None:
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
    stdout = payload.get("stdout", "")
    report_json: dict = {}
    for line in stdout.splitlines():
        if line.startswith("REPORT_JSON="):
            try:
                report_json = json.loads(line[len("REPORT_JSON="):])
            except (json.JSONDecodeError, ValueError):
                pass
            break
    lines = [
        f"# Weekly Security Scan — {date}",
        "",
        f"**Status:** {payload.get('status', 'unknown')}  **Exit code:** {payload.get('returncode', '?')}",
        "",
    ]
    if report_json:
        summary = report_json.get("summary", {})
        lines += [
            "## Summary",
            "",
            f"- Total endpoints: {summary.get('total', '?')}",
            f"- Passed: {summary.get('passed', '?')}",
            f"- Failed: {summary.get('failed', '?')}",
            f"- Warnings: {summary.get('warnings', '?')}",
            "",
        ]
    title = f"weekly-security-scan-{date}"[:100]
    markdown = "\n".join(lines)
    try:
        subprocess.run(
            [sys.executable, str(outline_tool), "document.publish",
             "--collection", "Security & Compliance", "--title", title],
            input=markdown, text=True, capture_output=True, check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ADR 0142 public surface security scan from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2))
