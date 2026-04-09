#!/usr/bin/env python3
"""ADR 0316 journey analytics and onboarding success scorecards."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import statistics
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable


SURFACE_ID = "windmill.operator_access_admin"
PLAUSIBLE_SITE_DOMAIN = "ops.localhost"
DEFAULT_WINDOW_DAYS = 30
LEDGER_RELATIVE_PATH = Path(".local/state/journey-analytics/operator-access-admin-events.jsonl")
LATEST_REPORT_RELATIVE_PATH = Path(".local/state/journey-analytics/operator-access-admin-latest.json")
GLITCHTIP_EVENT_URL_RELATIVE_PATH = Path(".local/glitchtip/platform-findings-event-url.txt")
CHECKLIST_ITEM_IDS = (
    "identity_access",
    "orientation",
    "safe_first_task",
    "search_success",
    "help_recovery",
)
PLAUSIBLE_ROUTE_PATHS = (
    "/journeys/operator-access-admin/start",
    "/journeys/operator-access-admin/checklist",
    "/journeys/operator-access-admin/search",
    "/journeys/operator-access-admin/search-result",
    "/journeys/operator-access-admin/help",
    "/journeys/operator-access-admin/help-success",
    "/journeys/operator-access-admin/alert",
    "/journeys/operator-access-admin/resume",
    "/journeys/operator-access-admin/safe-task",
)
FORBIDDEN_PROPERTY_TOKENS = (
    "email",
    "operator_id",
    "operator_name",
    "notes",
    "markdown",
    "query_text",
    "search_text",
    "stack",
    "trace",
)


SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def utc_now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> dt.datetime:
    if not value:
        raise ValueError("timestamp is required")
    normalized = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def resolve_repo_root(repo_root: str | Path | None = None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    env_root = os.environ.get("LV3_REPO_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    return Path.cwd()


def ledger_path_for(repo_root: Path) -> Path:
    return repo_root / LEDGER_RELATIVE_PATH


def latest_report_path_for(repo_root: Path) -> Path:
    return repo_root / LATEST_REPORT_RELATIVE_PATH


def glitchtip_event_url_path_for(repo_root: Path) -> Path:
    return repo_root / GLITCHTIP_EVENT_URL_RELATIVE_PATH


def ensure_json_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def sanitize_properties(value: Any) -> dict[str, str | int | float | bool | None]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str | int | float | bool | None] = {}
    for key, raw in value.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        lowered = key_text.lower()
        if any(token in lowered for token in FORBIDDEN_PROPERTY_TOKENS):
            raise ValueError(f"journey analytics property '{key_text}' is not permitted")
        sanitized = ensure_json_scalar(raw)
        if isinstance(sanitized, str):
            sanitized = sanitized.strip()
            if len(sanitized) > 160:
                sanitized = sanitized[:157] + "..."
        cleaned[key_text] = sanitized
        if len(cleaned) >= 20:
            break
    return cleaned


def compact_str(value: Any, *, max_length: int = 120) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def load_glitchtip_event_url(repo_root: Path) -> str | None:
    env_value = os.environ.get("LV3_JOURNEY_GLITCHTIP_EVENT_URL", "").strip()
    if env_value:
        return env_value
    secret_path = glitchtip_event_url_path_for(repo_root)
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip() or None
    return None


def build_glitchtip_payload(event: dict[str, Any]) -> dict[str, Any]:
    glitchtip = event.get("glitchtip") if isinstance(event.get("glitchtip"), dict) else {}
    properties = event.get("properties") if isinstance(event.get("properties"), dict) else {}
    return {
        "event_id": event["event_id"],
        "message": glitchtip.get("message")
        or f"Journey failure on {event.get('surface', SURFACE_ID)}: {event.get('milestone') or event.get('event_type')}",
        "level": compact_str(glitchtip.get("level"), max_length=24) or "error",
        "platform": "python",
        "tags": {
            "component": "journey-analytics",
            "surface": event.get("surface", SURFACE_ID),
            "event_type": event.get("event_type", ""),
            "stage": event.get("stage", ""),
            "milestone": event.get("milestone", ""),
            "route": event.get("route", ""),
            "alert_source": properties.get("alert_source", ""),
        },
        "extra": {
            "journey_event": event,
        },
    }


def normalize_glitchtip_event_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("glitchtip event url is required")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.username:
        project_id = parsed.path.rstrip("/").split("/")[-1]
        if not project_id:
            raise ValueError("glitchtip DSN must include a project id")
        prefix = parsed.path.rstrip("/")
        prefix = prefix[: -len(project_id)].rstrip("/")
        store_path = f"{prefix}/api/{project_id}/store/"
        query_items = [
            ("sentry_key", parsed.username),
            ("sentry_version", "7"),
            ("sentry_client", "journey-scorecards/1.0"),
        ]
        if parsed.password:
            query_items.append(("sentry_secret", parsed.password))
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urllib.parse.urlunsplit(
            (
                parsed.scheme,
                netloc,
                store_path,
                urllib.parse.urlencode(query_items),
                "",
            )
        )
    return raw


def post_json(url: str, payload: dict[str, Any]) -> None:
    request = urllib.request.Request(
        normalize_glitchtip_event_url(url),
        data=json.dumps(payload, sort_keys=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15):
        return None


def normalize_event(payload: dict[str, Any]) -> dict[str, Any]:
    event_type = compact_str(payload.get("event_type"), max_length=80)
    if not event_type:
        raise ValueError("journey analytics event_type is required")
    visitor_id = compact_str(payload.get("visitor_id"), max_length=80)
    session_id = compact_str(payload.get("session_id"), max_length=80)
    if not visitor_id or not session_id:
        raise ValueError("journey analytics visitor_id and session_id are required")
    event: dict[str, Any] = {
        "schema_version": 1,
        "event_id": compact_str(payload.get("event_id"), max_length=80) or uuid.uuid4().hex,
        "surface": compact_str(payload.get("surface"), max_length=80) or SURFACE_ID,
        "visitor_id": visitor_id,
        "session_id": session_id,
        "flow_id": compact_str(payload.get("flow_id"), max_length=80),
        "occurred_at": compact_str(payload.get("occurred_at"), max_length=40) or utc_now_iso(),
        "event_type": event_type,
        "stage": compact_str(payload.get("stage"), max_length=80),
        "milestone": compact_str(payload.get("milestone"), max_length=80),
        "result": compact_str(payload.get("result"), max_length=40),
        "route": compact_str(payload.get("route"), max_length=160),
        "checklist_item": compact_str(payload.get("checklist_item"), max_length=80),
        "duration_ms": None,
        "properties": sanitize_properties(payload.get("properties")),
        "plausible": {},
        "glitchtip": {"requested": False, "emitted": False},
        "recorded_at": utc_now_iso(),
    }
    duration_ms = payload.get("duration_ms")
    if duration_ms is not None:
        try:
            numeric_duration = int(duration_ms)
        except (TypeError, ValueError) as exc:
            raise ValueError("journey analytics duration_ms must be numeric") from exc
        if numeric_duration >= 0:
            event["duration_ms"] = numeric_duration

    plausible = payload.get("plausible") if isinstance(payload.get("plausible"), dict) else {}
    plausible_event_name = compact_str(plausible.get("event_name"), max_length=80)
    plausible_page_path = compact_str(plausible.get("page_path"), max_length=160)
    if plausible_event_name or plausible_page_path:
        event["plausible"] = {
            "site_domain": compact_str(plausible.get("site_domain"), max_length=80) or PLAUSIBLE_SITE_DOMAIN,
            "page_path": plausible_page_path,
            "event_name": plausible_event_name,
            "attempted": bool(plausible.get("attempted", True)),
        }

    glitchtip = payload.get("glitchtip") if isinstance(payload.get("glitchtip"), dict) else {}
    if glitchtip.get("requested"):
        event["glitchtip"] = {
            "requested": True,
            "emitted": False,
            "level": compact_str(glitchtip.get("level"), max_length=24) or "error",
            "message": compact_str(glitchtip.get("message"), max_length=160),
        }

    parse_timestamp(event["occurred_at"])
    if event["checklist_item"] and event["checklist_item"] not in CHECKLIST_ITEM_IDS:
        raise ValueError(f"unsupported checklist item: {event['checklist_item']}")
    return event


def append_event(repo_root: Path, event: dict[str, Any]) -> Path:
    ledger_path = ledger_path_for(repo_root)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return ledger_path


def record_event(
    repo_root: str | Path,
    payload: dict[str, Any],
    *,
    post_json_func: Callable[[str, dict[str, Any]], None] = post_json,
) -> dict[str, Any]:
    root = resolve_repo_root(repo_root)
    event = normalize_event(payload)
    glitchtip = event.get("glitchtip") if isinstance(event.get("glitchtip"), dict) else {}
    if glitchtip.get("requested"):
        event_url = load_glitchtip_event_url(root)
        if event_url:
            try:
                post_json_func(event_url, build_glitchtip_payload(event))
                glitchtip["emitted"] = True
            except (RuntimeError, urllib.error.URLError):
                glitchtip["emitted"] = False
                glitchtip["error"] = "delivery_failed"
        else:
            glitchtip["emitted"] = False
            glitchtip["error"] = "missing_event_url"
    event["glitchtip"] = glitchtip
    ledger_path = append_event(root, event)
    return {
        "status": "ok",
        "ledger_path": str(ledger_path),
        "event": event,
    }


def load_events(repo_root: str | Path) -> list[dict[str, Any]]:
    root = resolve_repo_root(repo_root)
    ledger_path = ledger_path_for(root)
    if not ledger_path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            items.append(payload)
    items.sort(key=lambda item: item.get("occurred_at", ""))
    return items


def median_seconds(values: Iterable[int]) -> int | None:
    sample = sorted(int(value) for value in values if value >= 0)
    if not sample:
        return None
    return int(statistics.median(sample))


def percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def filter_recent_events(events: list[dict[str, Any]], *, now: dt.datetime, window_days: int) -> list[dict[str, Any]]:
    cutoff = now - dt.timedelta(days=window_days)
    return [event for event in events if parse_timestamp(event.get("occurred_at")).astimezone(dt.timezone.utc) >= cutoff]


def build_population(events: list[dict[str, Any]]) -> dict[str, int]:
    visitors = {event.get("visitor_id") for event in events if event.get("visitor_id")}
    sessions = {event.get("session_id") for event in events if event.get("session_id")}
    return {
        "visitors": len(visitors),
        "sessions": len(sessions),
        "events": len(events),
    }


def score_time_to_first_safe_action(events: list[dict[str, Any]]) -> dict[str, Any]:
    started_at: dict[str, dt.datetime] = {}
    durations: list[int] = []
    for event in events:
        visitor_id = event.get("visitor_id")
        if not visitor_id:
            continue
        occurred_at = parse_timestamp(event.get("occurred_at"))
        if event.get("event_type") == "session_started" and visitor_id not in started_at:
            started_at[visitor_id] = occurred_at
        if event.get("event_type") == "safe_task_completed" and visitor_id in started_at:
            delta = int((occurred_at - started_at[visitor_id]).total_seconds())
            if delta >= 0:
                durations.append(delta)
                started_at.pop(visitor_id, None)
    return {
        "status": "ok",
        "sample_size": len(durations),
        "median_seconds": median_seconds(durations),
    }


def score_checklist_completion(events: list[dict[str, Any]]) -> dict[str, Any]:
    per_visitor: dict[str, dict[str, dt.datetime]] = {}
    started_visitors: set[str] = set()
    for event in events:
        visitor_id = event.get("visitor_id")
        if not visitor_id:
            continue
        if event.get("event_type") == "session_started":
            started_visitors.add(visitor_id)
        if event.get("event_type") != "checklist_item_completed":
            continue
        item_id = event.get("checklist_item")
        if item_id not in CHECKLIST_ITEM_IDS:
            continue
        completed = per_visitor.setdefault(visitor_id, {})
        completed.setdefault(item_id, parse_timestamp(event.get("occurred_at")))

    completion_durations: list[int] = []
    completed_visitors = 0
    for visitor_id in started_visitors:
        items = per_visitor.get(visitor_id, {})
        if any(item_id not in items for item_id in CHECKLIST_ITEM_IDS):
            continue
        completed_visitors += 1
        completion_durations.append(
            int((max(items.values()) - min(items.values())).total_seconds())
        )
    return {
        "status": "ok",
        "started_visitors": len(started_visitors),
        "completed_visitors": completed_visitors,
        "completion_rate": percent(completed_visitors, len(started_visitors)),
        "median_completion_seconds": median_seconds(completion_durations),
    }


def score_search_success(events: list[dict[str, Any]]) -> dict[str, Any]:
    started: dict[str, dt.datetime] = {}
    durations: list[int] = []
    for event in events:
        flow_id = event.get("flow_id")
        if not flow_id:
            continue
        occurred_at = parse_timestamp(event.get("occurred_at"))
        if event.get("event_type") == "search_started":
            started.setdefault(flow_id, occurred_at)
        if event.get("event_type") == "search_destination_opened" and flow_id in started:
            durations.append(int((occurred_at - started[flow_id]).total_seconds()))
    successful = len(durations)
    return {
        "status": "ok",
        "started_searches": len(started),
        "successful_searches": successful,
        "success_rate": percent(successful, len(started)),
        "median_success_seconds": median_seconds(durations),
    }


def score_alert_handoffs(events: list[dict[str, Any]]) -> dict[str, Any]:
    alerts: dict[str, dt.datetime] = {}
    acks: dict[str, dt.datetime] = {}
    resolutions: dict[str, dt.datetime] = {}
    for event in events:
        flow_id = event.get("flow_id")
        if not flow_id:
            continue
        occurred_at = parse_timestamp(event.get("occurred_at"))
        if event.get("event_type") == "alert_emitted":
            alerts.setdefault(flow_id, occurred_at)
        elif event.get("event_type") == "alert_acknowledged":
            acks.setdefault(flow_id, occurred_at)
        elif event.get("event_type") == "alert_resolved":
            resolutions.setdefault(flow_id, occurred_at)

    ack_durations = [
        int((acks[flow_id] - started_at).total_seconds())
        for flow_id, started_at in alerts.items()
        if flow_id in acks
    ]
    resolution_durations = [
        int((resolutions[flow_id] - started_at).total_seconds())
        for flow_id, started_at in alerts.items()
        if flow_id in resolutions
    ]
    return {
        "status": "ok",
        "alerts_emitted": len(alerts),
        "acknowledged_alerts": len(ack_durations),
        "resolved_alerts": len(resolution_durations),
        "median_acknowledgement_seconds": median_seconds(ack_durations),
        "median_resolution_seconds": median_seconds(resolution_durations),
    }


def score_resumable_tasks(events: list[dict[str, Any]]) -> dict[str, Any]:
    interrupted: set[str] = set()
    resumed: set[str] = set()
    completed_after_resume: set[str] = set()
    for event in events:
        flow_id = event.get("flow_id")
        if not flow_id:
            continue
        event_type = event.get("event_type")
        if event_type == "tour_dismissed":
            interrupted.add(flow_id)
        elif event_type == "tour_resumed":
            resumed.add(flow_id)
        elif event_type == "tour_completed" and flow_id in resumed:
            completed_after_resume.add(flow_id)
    return {
        "status": "ok",
        "interrupted_flows": len(interrupted),
        "resumed_flows": len(resumed),
        "completed_after_resume": len(completed_after_resume),
        "completion_rate": percent(len(completed_after_resume), len(interrupted)),
    }


def score_help_recovery(events: list[dict[str, Any]]) -> dict[str, Any]:
    opened: dict[str, dt.datetime] = {}
    completed: list[int] = []
    for event in events:
        flow_id = event.get("flow_id")
        if not flow_id:
            continue
        occurred_at = parse_timestamp(event.get("occurred_at"))
        if event.get("event_type") == "help_opened":
            opened.setdefault(flow_id, occurred_at)
        if event.get("event_type") == "help_task_completed" and flow_id in opened:
            completed.append(int((occurred_at - opened[flow_id]).total_seconds()))
    return {
        "status": "ok",
        "help_opens": len(opened),
        "successful_help_flows": len(completed),
        "success_rate": percent(len(completed), len(opened)),
        "median_success_seconds": median_seconds(completed),
    }


def query_plausible_route_counts(
    *,
    site_domain: str = PLAUSIBLE_SITE_DOMAIN,
    window_days: int = DEFAULT_WINDOW_DAYS,
    runner: SubprocessRunner = subprocess.run,
) -> dict[str, Any]:
    routes_json = json.dumps(list(PLAUSIBLE_ROUTE_PATHS))
    since_seconds = window_days * 24 * 60 * 60
    query = (
        "import Ecto.Query\n"
        f"site = Plausible.Sites.get_by_domain!(\"{site_domain}\")\n"
        f"routes = {routes_json}\n"
        f"since = DateTime.utc_now() |> DateTime.add(-{since_seconds}, :second)\n"
        "results = from(e in \"events_v2\", "
        "where: e.site_id == ^site.id and e.name == \"pageview\" and e.pathname in ^routes and e.timestamp >= ^since, "
        "group_by: e.pathname, "
        "select: %{pathname: e.pathname, count: count()}) "
        "|> Plausible.ClickhouseRepo.all()\n"
        "IO.puts(Jason.encode!(%{counts: results}))\n"
    )
    result = runner(
        ["docker", "exec", "plausible", "bin/plausible", "rpc", query],
        cwd="/",
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "status": "unavailable",
            "reason": "plausible_rpc_failed",
            "stderr": result.stderr.strip(),
        }
    parsed = json.loads(result.stdout.strip() or "{}")
    counts = {entry["pathname"]: int(entry["count"]) for entry in parsed.get("counts", [])}
    return {
        "status": "ok",
        "site_domain": site_domain,
        "window_days": window_days,
        "pageviews": {route: counts.get(route, 0) for route in PLAUSIBLE_ROUTE_PATHS},
    }


def build_scorecard_report(
    repo_root: str | Path,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    now: dt.datetime | None = None,
    plausible_route_provider: Callable[..., dict[str, Any]] = query_plausible_route_counts,
) -> dict[str, Any]:
    root = resolve_repo_root(repo_root)
    current_time = now or utc_now()
    events = filter_recent_events(load_events(root), now=current_time, window_days=window_days)
    glitchtip_count = sum(
        1
        for event in events
        if isinstance(event.get("glitchtip"), dict) and bool(event["glitchtip"].get("emitted"))
    )
    return {
        "status": "ok",
        "surface": SURFACE_ID,
        "generated_at": current_time.isoformat().replace("+00:00", "Z"),
        "window_days": window_days,
        "population": build_population(events),
        "scorecards": {
            "time_to_first_safe_action": score_time_to_first_safe_action(events),
            "onboarding_checklist_completion": score_checklist_completion(events),
            "search_to_destination_success": score_search_success(events),
            "alert_handoffs": score_alert_handoffs(events),
            "resumable_task_completion": score_resumable_tasks(events),
            "help_to_successful_recovery": score_help_recovery(events),
        },
        "route_aggregates": plausible_route_provider(window_days=window_days),
        "failure_signals": {
            "glitchtip_events": glitchtip_count,
        },
        "sources": {
            "ledger_path": str(ledger_path_for(root)),
            "latest_report_path": str(latest_report_path_for(root)),
            "plausible_site_domain": PLAUSIBLE_SITE_DOMAIN,
        },
    }


def write_latest_report(repo_root: str | Path, report: dict[str, Any]) -> Path:
    root = resolve_repo_root(repo_root)
    output_path = latest_report_path_for(root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ADR 0316 journey analytics and onboarding success scorecards.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser("record", help="Record one journey analytics event.")
    record_parser.add_argument("--repo-root", default=None)
    record_parser.add_argument("--event-json", required=True)

    report_parser = subparsers.add_parser("report", help="Render the current onboarding scorecards.")
    report_parser.add_argument("--repo-root", default=None)
    report_parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    report_parser.add_argument("--write-latest", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root)
    if args.command == "record":
        payload = json.loads(args.event_json)
        print(json.dumps(record_event(repo_root, payload), indent=2, sort_keys=True))
        return 0
    if args.command == "report":
        report = build_scorecard_report(repo_root, window_days=args.window_days)
        if args.write_latest:
            write_latest_report(repo_root, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
