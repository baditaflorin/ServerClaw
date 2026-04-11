#!/usr/bin/env python3
"""ADR 0118 — Weekly case-library quality audit.

Windmill entrypoint: run on a weekly schedule to:
  1. Flag resolved cases with a missing root_cause.
  2. Archive open cases older than 90 days.
  3. Optionally re-execute verification_command values and report failures.
  4. Post a summary to Mattermost if a webhook URL is supplied.

Returns a JSON report with summary counts.
"""

from __future__ import annotations

import os

import argparse
import importlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any


def _post_json_webhook(url: str, payload: dict[str, Any]) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 300:
            raise RuntimeError(f"Mattermost webhook POST failed with HTTP {response.status}")


def _render_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "**ADR 0118 case quality audit**",
        f"- cases reviewed: `{summary.get('cases_reviewed', 0)}`",
        f"- missing root cause: `{summary.get('missing_root_cause_count', 0)}`",
        f"- archived stale open cases: `{summary.get('archived_count', 0)}`",
        f"- verification checks: `{summary.get('verification_count', 0)}`",
    ]
    flagged = report.get("flagged_missing_root_cause", [])
    if flagged:
        lines.append("\n**Resolved cases missing root_cause:**")
        for item in flagged[:10]:
            lines.append(f"- `{item['case_id']}` — {item['title']} ({item['affected_service']})")
        if len(flagged) > 10:
            lines.append(f"- … and {len(flagged) - 10} more")
    failed_verifications = [r for r in report.get("verification_results", []) if r.get("status") == "fail"]
    if failed_verifications:
        lines.append("\n**Verification failures (fix may have regressed):**")
        for item in failed_verifications[:5]:
            lines.append(f"- `{item['case_id']}` exit={item.get('exit_code')}")
    return "\n".join(lines)


def _load_case_store(repo_root: Path):
    """Import scripts/cases from the mounted repo checkout."""
    scripts_dir = str(repo_root / "scripts")
    if scripts_dir in sys.path:
        sys.path.remove(scripts_dir)
    sys.path.insert(0, scripts_dir)
    existing = sys.modules.get("cases")
    if existing is not None and not str(getattr(existing, "__file__", "")).startswith(scripts_dir):
        for name in list(sys.modules):
            if name == "cases" or name.startswith("cases."):
                del sys.modules[name]
    return importlib.import_module("cases").CaseStore(
        path=repo_root / ".local" / "state" / "cases" / "failure_cases.json"
    )


# Windmill entrypoint.
def main(
    *,
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    verify_commands: bool = False,
    mattermost_webhook_url: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not (repo_root / "scripts").exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }
    store = _load_case_store(repo_root)
    report = store.audit_quality(verify_commands=verify_commands)
    report["status"] = "ok"

    if mattermost_webhook_url:
        _post_json_webhook(mattermost_webhook_url, {"text": _render_summary(report)})
        report["mattermost_posted"] = True
    else:
        report["mattermost_posted"] = False

    return report


# ------------------------------------------------------------------
# CLI wrapper
# ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0118 case-quality audit.")
    parser.add_argument(
        "--repo-path",
        default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
        help="Path to the repo checkout on this machine.",
    )
    parser.add_argument(
        "--verify-commands",
        action="store_true",
        help="Re-execute verification_command for each case that has one.",
    )
    parser.add_argument(
        "--mattermost-webhook-url",
        default=None,
        help="Incoming webhook URL for posting the audit summary to Mattermost.",
    )
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                verify_commands=args.verify_commands,
                mattermost_webhook_url=args.mattermost_webhook_url,
            ),
            indent=2,
            sort_keys=True,
        )
    )
