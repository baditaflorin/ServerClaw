from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(monkeypatch: pytest.MonkeyPatch, repo_root: Path):
    monkeypatch.setenv("LV3_REPO_ROOT", str(repo_root))
    import journey_scorecards

    return importlib.reload(journey_scorecards)


def test_record_event_writes_ledger_and_glitchtip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module(monkeypatch, tmp_path)
    secret_path = tmp_path / ".local" / "glitchtip" / "platform-findings-event-url.txt"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text("https://glitchtip.example", encoding="utf-8")

    delivered: list[tuple[str, dict]] = []

    payload = module.record_event(
        tmp_path,
        {
            "event_type": "alert_emitted",
            "visitor_id": "visitor-1",
            "session_id": "session-1",
            "occurred_at": "2026-04-02T08:00:00Z",
            "stage": "alert",
            "milestone": "inventory",
            "result": "error",
            "flow_id": "flow-1",
            "route": "https://ops.lv3.org/journeys/operator-access-admin/alert",
            "properties": {"alert_source": "inventory"},
            "glitchtip": {"requested": True, "message": "Inventory alert"},
        },
        post_json_func=lambda url, event: delivered.append((url, event)),
    )

    assert payload["status"] == "ok"
    assert delivered[0][0] == "https://glitchtip.example"
    assert delivered[0][1]["message"] == "Inventory alert"

    ledger_path = tmp_path / ".local" / "state" / "journey-analytics" / "operator-access-admin-events.jsonl"
    event = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    assert event["glitchtip"]["requested"] is True
    assert event["glitchtip"]["emitted"] is True
    assert event["properties"]["alert_source"] == "inventory"


def test_sensitive_properties_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="operator_id"):
        module.normalize_event(
            {
                "event_type": "search_started",
                "visitor_id": "visitor-1",
                "session_id": "session-1",
                "properties": {"operator_id": "alice"},
            }
        )


def test_scorecard_report_aggregates_metrics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module(monkeypatch, tmp_path)

    def record(event_type: str, occurred_at: str, **extra) -> None:
        module.record_event(
            tmp_path,
            {
                "event_type": event_type,
                "visitor_id": "visitor-1",
                "session_id": "session-1",
                "occurred_at": occurred_at,
                **extra,
            },
            post_json_func=lambda url, payload: None,
        )

    record("session_started", "2026-04-02T08:00:00Z", stage="identity_access", milestone="authenticated_session_ready")
    record("tour_started", "2026-04-02T08:00:30Z", stage="orientation", milestone="first_run", flow_id="tour-1")
    record("tour_dismissed", "2026-04-02T08:00:40Z", stage="orientation", milestone="first_run", flow_id="tour-1")
    record("tour_resumed", "2026-04-02T08:00:50Z", stage="orientation", milestone="first_run", flow_id="tour-1")
    record("tour_completed", "2026-04-02T08:01:10Z", stage="orientation", milestone="first_run", flow_id="tour-1")
    record(
        "checklist_item_completed",
        "2026-04-02T08:01:10Z",
        checklist_item="orientation",
        stage="orientation",
        milestone="first_run",
    )
    record("safe_task_completed", "2026-04-02T08:02:00Z", stage="safe_first_task", milestone="inventory_reviewed")
    record(
        "checklist_item_completed",
        "2026-04-02T08:02:00Z",
        checklist_item="safe_first_task",
        stage="safe_first_task",
        milestone="inventory_reviewed",
    )
    record("search_started", "2026-04-02T08:02:10Z", stage="search", flow_id="search-1")
    record(
        "search_destination_opened",
        "2026-04-02T08:02:40Z",
        stage="search",
        milestone="inventory_destination_opened",
        flow_id="search-1",
    )
    record(
        "checklist_item_completed",
        "2026-04-02T08:02:40Z",
        checklist_item="search_success",
        stage="search",
        milestone="inventory_destination_opened",
    )
    record("help_opened", "2026-04-02T08:03:00Z", stage="help", flow_id="help-1")
    record(
        "help_task_completed",
        "2026-04-02T08:04:00Z",
        stage="help",
        milestone="inventory_reviewed",
        flow_id="help-1",
    )
    record(
        "checklist_item_completed",
        "2026-04-02T08:04:00Z",
        checklist_item="help_recovery",
        stage="help",
        milestone="inventory_reviewed",
    )
    record(
        "alert_emitted",
        "2026-04-02T08:04:10Z",
        stage="alert",
        milestone="inventory",
        flow_id="alert-1",
        glitchtip={"requested": True},
    )
    record(
        "alert_acknowledged",
        "2026-04-02T08:04:20Z",
        stage="alert",
        milestone="inventory",
        flow_id="alert-1",
    )
    record(
        "alert_resolved",
        "2026-04-02T08:05:20Z",
        stage="alert",
        milestone="inventory_refreshed",
        flow_id="alert-1",
    )
    record(
        "checklist_item_completed",
        "2026-04-02T08:00:05Z",
        checklist_item="identity_access",
        stage="identity_access",
        milestone="authenticated_session_ready",
    )

    report = module.build_scorecard_report(
        tmp_path,
        now=module.parse_timestamp("2026-04-03T08:00:00Z"),
        plausible_route_provider=lambda **kwargs: {
            "status": "ok",
            "pageviews": {
                "/journeys/operator-access-admin/start": 4,
                "/journeys/operator-access-admin/help": 2,
            },
        },
    )

    assert report["population"]["visitors"] == 1
    assert report["scorecards"]["time_to_first_safe_action"]["median_seconds"] == 120
    assert report["scorecards"]["search_to_destination_success"]["success_rate"] == 100.0
    assert report["scorecards"]["alert_handoffs"]["median_acknowledgement_seconds"] == 10
    assert report["scorecards"]["alert_handoffs"]["median_resolution_seconds"] == 70
    assert report["scorecards"]["resumable_task_completion"]["completion_rate"] == 100.0
    assert report["scorecards"]["help_to_successful_recovery"]["median_success_seconds"] == 60
    assert report["route_aggregates"]["pageviews"]["/journeys/operator-access-admin/start"] == 4
