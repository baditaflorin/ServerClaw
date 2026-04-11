from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windmill_defaults_seed_deadlock_detector_script_and_schedule() -> None:
    defaults = yaml.safe_load(
        (
            REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml"
        ).read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule_map = {entry["path"]: entry for entry in defaults["windmill_seed_schedules"]}

    assert "f/lv3/detect_deadlocks" in script_paths
    assert "f/lv3/detect_deadlocks_every_30s" in schedule_map
    assert schedule_map["f/lv3/detect_deadlocks_every_30s"]["enabled"] is True
    assert schedule_map["f/lv3/detect_deadlocks_every_30s"]["script_path"] == "f/lv3/detect_deadlocks"


def test_deadlock_events_and_ledger_type_are_registered() -> None:
    taxonomy = (REPO_ROOT / "config" / "event-taxonomy.yaml").read_text(encoding="utf-8")
    ledger_event_types = (REPO_ROOT / "config" / "ledger-event-types.yaml").read_text(encoding="utf-8")

    assert "platform.execution.deadlock_detected" in taxonomy
    assert "platform.execution.deadlock_aborted" in taxonomy
    assert "platform.execution.livelock_detected" in taxonomy
    assert "- execution.deadlock_aborted" in ledger_event_types
