#!/usr/bin/env python3
"""Windmill workflow: Reconcile Portal Artifacts (ADR 0399 Tier 1).

Detects drift across all four operator-facing portals (homepage, ops,
docs, changelog) and regenerates stale artifacts from their canonical
data sources.  Optionally posts a summary to Mattermost.

Schedule: every 15 minutes (recommended).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


def _post_mattermost(webhook_url: str, markdown: str) -> None:
    """Post a message to Mattermost via incoming webhook."""
    payload = json.dumps({"text": markdown}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 300:
                sys.stderr.write(f"Mattermost webhook returned HTTP {response.status}\n")
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Mattermost webhook failed: {exc}\n")


def _run_cli(repo_root: Path, subcommand: str, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the reconciliation CLI as a subprocess."""
    cmd = [
        sys.executable,
        "-m",
        "scripts.reconciliation.cli",
        subcommand,
    ]
    if extra_args:
        cmd += extra_args
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
    return subprocess.run(
        cmd,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
        env=env,
        timeout=600,
    )


def _build_markdown(
    drift_result: dict[str, Any],
    reconcile_result: dict[str, Any] | None,
    dry_run: bool,
) -> str:
    """Build a Mattermost-friendly markdown summary."""
    lines: list[str] = []
    lines.append("#### Portal Reconciliation Report")
    lines.append("")

    if not drift_result.get("any_drifted"):
        lines.append("All portals are in sync -- no regeneration needed.")
        return "\n".join(lines)

    # Drift details
    drifted_portals = [r["portal"] for r in drift_result.get("results", []) if r.get("drifted")]
    lines.append(f"**Drift detected** in {len(drifted_portals)} portal(s): `{'`, `'.join(drifted_portals)}`")
    lines.append("")

    if dry_run:
        lines.append("_Dry-run mode -- no regeneration was performed._")
        return "\n".join(lines)

    if reconcile_result is None:
        lines.append("_Regeneration was not attempted._")
        return "\n".join(lines)

    succeeded = reconcile_result.get("portals_regenerated", 0)
    failed = reconcile_result.get("portals_failed", 0)

    lines.append(f"**Regeneration**: {succeeded} succeeded, {failed} failed")
    lines.append("")

    for r in reconcile_result.get("results", []):
        icon = ":white_check_mark:" if r.get("success") else ":x:"
        detail = r.get("error") or "success"
        lines.append(f"- {icon} **{r['portal']}**: {detail}")

    return "\n".join(lines)


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    mattermost_webhook: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Reconcile all portal artifacts from canonical catalogs.

    Intended to run on a 15-minute cron schedule via Windmill.
    Detects drift, regenerates stale portals, and optionally posts
    a summary to Mattermost.
    """
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    cli_script = repo_root / "scripts" / "reconciliation" / "cli.py"
    if not cli_script.exists():
        return {
            "status": "blocked",
            "reason": "reconciliation CLI not found in worker checkout",
            "expected_path": str(cli_script),
        }

    # Step 1: Check drift across all portals
    drift_proc = _run_cli(repo_root, "check-drift")
    try:
        drift_result = json.loads(drift_proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "status": "error",
            "reason": "check-drift returned non-JSON output",
            "command": f"python -m scripts.reconciliation.cli check-drift",
            "returncode": drift_proc.returncode,
            "stdout": drift_proc.stdout.strip(),
            "stderr": drift_proc.stderr.strip(),
        }

    any_drifted = drift_result.get("any_drifted", False)
    reconcile_result: dict[str, Any] | None = None

    # Step 2: If drift detected and not dry-run, regenerate all portals
    if any_drifted and not dry_run:
        regen_proc = _run_cli(repo_root, "reconcile-all")
        try:
            reconcile_result = json.loads(regen_proc.stdout)
        except (json.JSONDecodeError, ValueError):
            return {
                "status": "error",
                "reason": "reconcile-all returned non-JSON output",
                "command": f"python -m scripts.reconciliation.cli reconcile-all",
                "returncode": regen_proc.returncode,
                "stdout": regen_proc.stdout.strip(),
                "stderr": regen_proc.stderr.strip(),
                "drift_result": drift_result,
            }

    # Step 3: Build markdown summary
    markdown = _build_markdown(drift_result, reconcile_result, dry_run)

    # Step 4: Post to Mattermost if webhook provided and changes were detected
    webhook = mattermost_webhook or os.environ.get("LV3_MATTERMOST_WEBHOOK", "")
    if webhook and any_drifted:
        _post_mattermost(webhook, markdown)

    # Build response
    status = "ok"
    if reconcile_result and reconcile_result.get("portals_failed", 0) > 0:
        status = "partial"

    return {
        "status": status,
        "channel": "#platform-ops",
        "any_drifted": any_drifted,
        "dry_run": dry_run,
        "portals_checked": drift_result.get("portals_checked", 0),
        "portals_regenerated": reconcile_result.get("portals_regenerated", 0) if reconcile_result else 0,
        "portals_failed": reconcile_result.get("portals_failed", 0) if reconcile_result else 0,
        "drift_result": drift_result,
        "reconcile_result": reconcile_result,
        "markdown": markdown,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reconcile all platform portal artifacts (ADR 0399 Tier 1).",
    )
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--mattermost-webhook", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = main(
        repo_path=args.repo_path,
        mattermost_webhook=args.mattermost_webhook,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
