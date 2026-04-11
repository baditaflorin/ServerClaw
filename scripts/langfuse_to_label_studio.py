#!/usr/bin/env python3
"""Push Langfuse traces into Label Studio as annotation tasks.

Queries Langfuse for recent traces that need human review, deduplicates
against already-imported tasks (via Label Studio task metadata), and
creates new annotation tasks in the target project.

Filtering strategy:
  - Traces with no score (unreviewed by automated eval)
  - Traces with any score below --min-score (flagged for review)
  - Traces tagged with "needs-review"
  - Traces from the last --lookback-hours window

Usage:
    python scripts/langfuse_to_label_studio.py sync \\
        --ls-base-url https://annotate.localhost \\
        --ls-token-file .local/label-studio/admin-token.txt \\
        --ls-project-title "Langfuse Trace Review" \\
        --langfuse-base-url https://langfuse.localhost \\
        --langfuse-public-key pk-lf-... \\
        --langfuse-secret-key-file .local/langfuse/project-secret-key.txt \\
        --lookback-hours 24 \\
        --min-score 0.7 \\
        --report-file .local/label-studio/sync-report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any
from urllib import error, parse, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

DEDUP_META_KEY = "lv3_langfuse_trace_id"
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MIN_SCORE = 0.7
DEFAULT_PAGE_SIZE = 50


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only, no third-party deps)
# ---------------------------------------------------------------------------


def _http(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any = None,
    basic_auth: tuple[str, str] | None = None,
    expected_status: tuple[int, ...] = (200,),
    timeout: int = 30,
) -> Any:
    encoded = json.dumps(body).encode() if body is not None else None
    hdrs: dict[str, str] = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if encoded is not None:
        hdrs["Content-Type"] = "application/json"
    if basic_auth:
        import base64

        creds = base64.b64encode(f"{basic_auth[0]}:{basic_auth[1]}".encode()).decode()
        hdrs["Authorization"] = f"Basic {creds}"
    req = request.Request(url, data=encoded, headers=hdrs, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            payload = resp.read().decode()
    except error.HTTPError as exc:
        status = exc.code
        payload = exc.read().decode(errors="replace")
    if status not in expected_status:
        raise RuntimeError(f"{method} {url} → {status}: {payload[:300]}")
    return json.loads(payload) if payload else None


def ls_get(base: str, path: str, token: str) -> Any:
    return _http("GET", f"{base}{path}", headers={"Authorization": f"Token {token}"})


def ls_post(base: str, path: str, token: str, body: Any, expected: tuple[int, ...] = (200, 201)) -> Any:
    return _http(
        "POST", f"{base}{path}", headers={"Authorization": f"Token {token}"}, body=body, expected_status=expected
    )


def lf_get(base: str, path: str, public_key: str, secret_key: str) -> Any:
    return _http("GET", f"{base}{path}", basic_auth=(public_key, secret_key))


# ---------------------------------------------------------------------------
# Langfuse helpers
# ---------------------------------------------------------------------------


def fetch_langfuse_traces(
    base_url: str,
    public_key: str,
    secret_key: str,
    from_timestamp: datetime,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Return all traces newer than from_timestamp."""
    traces: list[dict[str, Any]] = []
    page = 1
    from_str = from_timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    while True:
        params = parse.urlencode(
            {
                "page": page,
                "limit": page_size,
                "fromTimestamp": from_str,
                "orderBy": "timestamp.desc",
            }
        )
        payload = lf_get(base_url, f"/api/public/traces?{params}", public_key, secret_key)
        if not isinstance(payload, dict):
            break
        batch: list[dict[str, Any]] = payload.get("data", [])
        traces.extend(batch)
        meta = payload.get("meta", {})
        total_pages = meta.get("totalPages", 1)
        if page >= total_pages or not batch:
            break
        page += 1
    return traces


def trace_needs_review(trace: dict[str, Any], min_score: float) -> bool:
    """Return True if this trace should be sent to Label Studio."""
    tags: list[str] = trace.get("tags") or []
    if "needs-review" in tags:
        return True
    if "skip-review" in tags:
        return False
    scores: list[dict[str, Any]] = trace.get("scores") or []
    if not scores:
        return True  # unscored → always review
    for score in scores:
        value = score.get("value")
        if isinstance(value, (int, float)) and value < min_score:
            return True
    return False


def build_label_studio_task(
    trace: dict[str, Any],
    langfuse_base_url: str,
    langfuse_project_id: str,
) -> dict[str, Any]:
    """Map a Langfuse trace dict to a Label Studio task dict."""
    trace_id = trace.get("id", "")
    trace_url = f"{langfuse_base_url.rstrip('/')}/project/{langfuse_project_id}/traces/{trace_id}"

    # Extract prompt/response from trace input/output
    raw_input = trace.get("input") or {}
    raw_output = trace.get("output") or {}

    def _str(v: Any) -> str:
        if isinstance(v, str):
            return v
        return json.dumps(v, ensure_ascii=False)

    # Try common key names for prompt
    prompt = (
        raw_input.get("prompt")
        or raw_input.get("question")
        or raw_input.get("task")
        or raw_input.get("content")
        or raw_input.get("user")
        or _str(raw_input)
    )
    response = (
        raw_output.get("response")
        or raw_output.get("answer")
        or raw_output.get("result")
        or raw_output.get("content")
        or raw_output.get("assistant")
        or _str(raw_output)
    )

    scores: list[dict[str, Any]] = trace.get("scores") or []
    score_summary = {s.get("name", "score"): s.get("value") for s in scores if s.get("value") is not None}

    return {
        # Data keys for the Label Studio label config
        "prompt": str(prompt)[:4000],
        "response": str(response)[:4000],
        # Metadata shown in the UI and used for deduplication
        "meta": {
            DEDUP_META_KEY: trace_id,
            "trace_url": trace_url,
            "trace_name": trace.get("name", ""),
            "agent": trace.get("userId") or trace.get("sessionId") or "serverclaw",
            "timestamp": trace.get("timestamp", ""),
            "scores": score_summary,
            "tags": trace.get("tags") or [],
        },
    }


# ---------------------------------------------------------------------------
# Label Studio helpers
# ---------------------------------------------------------------------------


def find_ls_project(base_url: str, token: str, title: str) -> dict[str, Any] | None:
    page = 1
    while True:
        params = parse.urlencode({"page": page, "page_size": 50})
        payload = ls_get(base_url, f"/api/projects?{params}", token)
        results: list[dict[str, Any]] = payload.get("results", []) if isinstance(payload, dict) else payload or []
        for project in results:
            if str(project.get("title", "")).strip() == title:
                return project
        if not payload.get("next") if isinstance(payload, dict) else not results:
            break
        page += 1
    return None


def fetch_existing_trace_ids(base_url: str, token: str, project_id: int) -> set[str]:
    """Return the set of Langfuse trace IDs already imported into this project."""
    ids: set[str] = set()
    page = 1
    while True:
        params = parse.urlencode({"project": project_id, "page": page, "page_size": 100})
        payload = ls_get(base_url, f"/api/tasks?{params}", token)
        if isinstance(payload, dict):
            tasks: list[dict[str, Any]] = payload.get("tasks", [])
        elif isinstance(payload, list):
            tasks = payload
        else:
            break
        for task in tasks:
            data = task.get("data") or {}
            meta = data.get("meta") or {}
            tid = meta.get(DEDUP_META_KEY)
            if tid:
                ids.add(tid)
        has_next = payload.get("next") if isinstance(payload, dict) else False
        if not has_next or not tasks:
            break
        page += 1
    return ids


def import_tasks(base_url: str, token: str, project_id: int, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return ls_post(base_url, f"/api/projects/{project_id}/import", token, tasks)


# ---------------------------------------------------------------------------
# Main sync logic
# ---------------------------------------------------------------------------


def run_sync(
    ls_base_url: str,
    ls_token: str,
    ls_project_title: str,
    langfuse_base_url: str,
    langfuse_public_key: str,
    langfuse_secret_key: str,
    langfuse_project_id: str,
    lookback_hours: int,
    min_score: float,
) -> dict[str, Any]:
    from_ts = datetime.now(UTC) - timedelta(hours=lookback_hours)

    # 1. Find target Label Studio project
    project = find_ls_project(ls_base_url, ls_token, ls_project_title)
    if project is None:
        raise RuntimeError(
            f"Label Studio project {ls_project_title!r} not found at {ls_base_url}. "
            "Run the label-studio Ansible playbook first."
        )
    project_id: int = project["id"]

    # 2. Fetch traces from Langfuse
    all_traces = fetch_langfuse_traces(langfuse_base_url, langfuse_public_key, langfuse_secret_key, from_ts)

    # 3. Filter to traces that need review
    review_traces = [t for t in all_traces if trace_needs_review(t, min_score)]

    # 4. Deduplicate against already-imported tasks
    existing_ids = fetch_existing_trace_ids(ls_base_url, ls_token, project_id)
    new_traces = [t for t in review_traces if t.get("id", "") not in existing_ids]

    # 5. Build and import tasks
    tasks = [build_label_studio_task(t, langfuse_base_url, langfuse_project_id) for t in new_traces]
    imported = 0
    if tasks:
        result = import_tasks(ls_base_url, ls_token, project_id, tasks)
        imported = result.get("task_count", len(tasks)) if isinstance(result, dict) else len(tasks)

    return {
        "status": "ok",
        "project_id": project_id,
        "project_title": ls_project_title,
        "traces_fetched": len(all_traces),
        "traces_needing_review": len(review_traces),
        "already_imported": len(review_traces) - len(new_traces),
        "newly_imported": imported,
        "lookback_hours": lookback_hours,
        "min_score": min_score,
        "from_timestamp": from_ts.isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Langfuse traces to Label Studio for human review.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_p = subparsers.add_parser("sync", help="Import new traces into Label Studio.")
    sync_p.add_argument("--ls-base-url", required=True)
    sync_p.add_argument("--ls-token-file", required=True)
    sync_p.add_argument("--ls-project-title", default="Langfuse Trace Review")
    sync_p.add_argument("--langfuse-base-url", default="https://langfuse.localhost")
    sync_p.add_argument("--langfuse-public-key")
    sync_p.add_argument("--langfuse-secret-key-file")
    sync_p.add_argument("--langfuse-project-id", default="lv3-agent-observability")
    sync_p.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    sync_p.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    sync_p.add_argument("--report-file")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    ls_token = Path(args.ls_token_file).read_text().strip()
    if not ls_token:
        raise ValueError("Label Studio token file is empty")

    # Langfuse keys: CLI arg or fall back to repo config
    public_key = args.langfuse_public_key
    secret_key = None
    if args.langfuse_secret_key_file:
        secret_key = Path(args.langfuse_secret_key_file).read_text().strip()

    if not public_key or not secret_key:
        try:
            if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
                del sys.modules["platform"]
            from platform.llm.observability import load_langfuse_config  # type: ignore[import]

            cfg = load_langfuse_config(REPO_ROOT)
            public_key = public_key or cfg.public_key
            secret_key = secret_key or cfg.secret_key
        except Exception as exc:
            raise ValueError(f"Could not load Langfuse credentials: {exc}") from exc

    report = run_sync(
        ls_base_url=args.ls_base_url.rstrip("/"),
        ls_token=ls_token,
        ls_project_title=args.ls_project_title,
        langfuse_base_url=args.langfuse_base_url.rstrip("/"),
        langfuse_public_key=public_key,
        langfuse_secret_key=secret_key,
        langfuse_project_id=args.langfuse_project_id,
        lookback_hours=args.lookback_hours,
        min_score=args.min_score,
    )

    if args.report_file:
        Path(args.report_file).write_text(json.dumps(report, indent=2) + "\n")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        raise
