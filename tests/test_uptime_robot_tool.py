from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import uptime_robot_tool as tool


def test_alert_contact_spec_formats_threshold_and_recurrence():
    assert tool.alert_contact_spec(123) == "123_0_0"
    assert tool.alert_contact_spec(456, threshold=5, recurrence=10) == "456_5_10"


def test_normalize_monitor_expands_alert_contact_ids():
    payload = tool.normalize_monitor(
        {
            "friendly_name": "lv3 Public Status Page",
            "type": 1,
            "url": "https://status.example.com",
            "interval": 300,
            "alert_contacts": ["ops-email", "ops-webhook"],
        },
        {"ops-email": 12, "ops-webhook": 34},
    )

    assert payload["alert_contacts"] == "12_0_0-34_0_0"
    assert payload["interval"] == 300


def test_resolve_contact_value_reads_controller_local_secret(tmp_path: Path):
    secret_file = tmp_path / "webhook.txt"
    secret_file.write_text("https://mattermost.example/hooks/test\n", encoding="utf-8")

    value = tool.resolve_contact_value(
        {
            "friendly_name": "ops-webhook",
            "type": 5,
            "value_secret_id": "uptime_robot_mattermost_webhook",
        },
        {"uptime_robot_mattermost_webhook": secret_file},
    )

    assert value == "https://mattermost.example/hooks/test"
