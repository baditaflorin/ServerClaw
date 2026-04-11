#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.risk_scorer import assemble_context, compile_workflow_intent, score_intent


def parse_recorded_at(payload: dict[str, Any]) -> datetime | None:
    for key in ("recorded_on", "applied_on"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            if "T" in value:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def receipt_outcome(payload: dict[str, Any]) -> str:
    verification = payload.get("verification", [])
    if not isinstance(verification, list) or not verification:
        return "no_data"
    failed = any(
        isinstance(item, dict) and str(item.get("result", "")).strip().lower() not in {"pass", "ok"}
        for item in verification
    )
    return "incident" if failed else "success"


def bucket_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = defaultdict(list)
    for row in rows:
        buckets[row["risk_class"]].append(row)

    summary = []
    for risk_class in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        bucket = buckets.get(risk_class, [])
        total = len(bucket)
        if total == 0:
            summary.append(
                {
                    "risk_class": risk_class,
                    "changes": 0,
                    "false_negative_rate": "no data",
                    "false_positive_rate": "no data",
                }
            )
            continue
        incidents = sum(1 for row in bucket if row["outcome"] == "incident")
        successes = sum(1 for row in bucket if row["outcome"] == "success")
        false_negative_rate: str | float = "no data"
        false_positive_rate: str | float = "no data"
        if risk_class == "LOW":
            false_negative_rate = round(incidents / total, 3)
        if risk_class == "CRITICAL":
            false_positive_rate = round(successes / total, 3)
        summary.append(
            {
                "risk_class": risk_class,
                "changes": total,
                "false_negative_rate": false_negative_rate,
                "false_positive_rate": false_positive_rate,
            }
        )
    return summary


def format_report(rows: list[dict[str, Any]], summary: list[dict[str, Any]], lookback_days: int) -> str:
    lines = [
        f"Risk scoring calibration report ({lookback_days}d lookback)",
        "",
        f"Changes analysed: {len(rows)}",
    ]
    for item in summary:
        lines.append(
            "- "
            + f"{item['risk_class']}: changes={item['changes']}, "
            + f"false_negative_rate={item['false_negative_rate']}, "
            + f"false_positive_rate={item['false_positive_rate']}"
        )
    return "\n".join(lines)


def post_to_mattermost(webhook_url: str, text: str) -> None:
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 300:
            raise RuntimeError(f"Mattermost webhook returned HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate ADR 0116 risk scoring weights from recent live-apply receipts."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--mattermost-webhook-url")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    cutoff = datetime.now(UTC) - timedelta(days=args.lookback_days)
    rows: list[dict[str, Any]] = []
    for receipt in sorted((repo_root / "receipts" / "live-applies").glob("*.json")):
        payload = json.loads(receipt.read_text())
        recorded_at = parse_recorded_at(payload)
        if recorded_at is None or recorded_at < cutoff:
            continue
        workflow_id = payload.get("workflow_id")
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            continue
        intent_seed = compile_workflow_intent(workflow_id, {}, repo_root=repo_root)
        context = assemble_context(intent_seed, repo_root=repo_root, now=recorded_at)
        risk = score_intent(intent_seed, context, repo_root=repo_root)
        rows.append(
            {
                "receipt": receipt.name,
                "workflow_id": workflow_id,
                "risk_class": risk.final_risk_class.value,
                "score": round(risk.score, 2),
                "outcome": receipt_outcome(payload),
            }
        )

    summary = bucket_rows(rows)
    report = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "lookback_days": args.lookback_days,
        "changes_analyzed": len(rows),
        "summary": summary,
        "rows": rows,
    }
    print(json.dumps(report, indent=2))

    webhook_url = args.mattermost_webhook_url
    if webhook_url:
        post_to_mattermost(webhook_url, format_report(rows, summary, args.lookback_days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
