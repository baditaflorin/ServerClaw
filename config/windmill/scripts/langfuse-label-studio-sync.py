#!/usr/bin/env python3
"""Windmill scheduled job: sync Langfuse traces → Label Studio for human review.

Runs on a schedule (e.g. every 30 minutes) and pushes unreviewed or
low-scored Langfuse traces into the Label Studio annotation queue so
human operators can label agent decisions as good / bad / needs_follow_up.

Windmill inputs:
  lookback_hours  int   default=2    Hours of history to scan per run
  min_score       float default=0.7  Import traces with any score below this
  dry_run         bool  default=False If true, report plan without importing
  repo_path       str   default="/srv/proxmox_florin_server"
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import Any


def main(
    lookback_hours: int = 2,
    min_score: float = 0.7,
    dry_run: bool = False,
    repo_path: str = "/srv/proxmox_florin_server",
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    script = repo_root / "scripts" / "langfuse_to_label_studio.py"
    if not script.exists():
        return {"status": "blocked", "reason": f"sync script not found at {script}"}

    ls_token_file = repo_root / ".local" / "label-studio" / "admin-token.txt"
    lf_secret_file = repo_root / ".local" / "langfuse" / "project-secret-key.txt"
    lf_public_key_file = repo_root / ".local" / "langfuse" / "project-public-key.txt"

    for f in (ls_token_file, lf_secret_file, lf_public_key_file):
        if not f.exists():
            return {"status": "blocked", "reason": f"required credential file missing: {f}"}

    if dry_run:
        return {
            "status": "dry_run",
            "would_run": str(script),
            "lookback_hours": lookback_hours,
            "min_score": min_score,
        }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as report_fh:
        report_path = Path(report_fh.name)

    cmd = [
        "python3", str(script), "sync",
        # Use internal URLs — Windmill workers are on the 10.10.10.x network
        "--ls-base-url", "http://10.10.10.20:8110",
        "--ls-token-file", str(ls_token_file),
        "--ls-project-title", "Langfuse Trace Review",
        "--langfuse-base-url", "http://10.10.10.20:3002",
        "--langfuse-public-key", lf_public_key_file.read_text().strip(),
        "--langfuse-secret-key-file", str(lf_secret_file),
        "--langfuse-project-id", "lv3-agent-observability",
        "--lookback-hours", str(lookback_hours),
        "--min-score", str(min_score),
        "--report-file", str(report_path),
    ]

    env = {**os.environ, "PYTHONPATH": f"{repo_root}:{os.environ.get('PYTHONPATH', '')}"}

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        report: dict[str, Any] = {}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text())
            except json.JSONDecodeError:
                pass
        report_path.unlink(missing_ok=True)

        if proc.returncode != 0:
            return {
                "status": "error",
                "exit_code": proc.returncode,
                "stderr": proc.stderr[-1000:],
                "stdout": proc.stdout[-500:],
            }
        return {"status": "ok", **report}

    except subprocess.TimeoutExpired:
        return {"status": "error", "reason": "script timed out after 120s"}
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}
