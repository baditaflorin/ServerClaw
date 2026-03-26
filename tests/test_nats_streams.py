from __future__ import annotations

from scripts.nats_streams import DesiredStream, diff_streams, parse_duration


def test_parse_duration_supports_expected_units() -> None:
    assert parse_duration("2m") == 120
    assert parse_duration("90d") == 90 * 24 * 60 * 60


def test_diff_streams_reports_only_changed_fields() -> None:
    desired = DesiredStream(
        name="PLATFORM_EVENTS",
        subjects=("platform.>",),
        retention="limits",
        max_age_seconds=7776000,
        storage="file",
        replicas=1,
        discard="old",
        duplicate_window_seconds=120,
    )
    live = {
        "name": "PLATFORM_EVENTS",
        "subjects": ["platform.>"],
        "retention": "limits",
        "max_age_seconds": 7776000,
        "storage": "memory",
        "replicas": 1,
        "discard": "old",
        "duplicate_window_seconds": 120,
        "description": None,
    }

    diff = diff_streams(desired, live)

    assert diff == {
        "storage": {"desired": "file", "live": "memory"},
    }
