"""Behaviour tests for the external Scanopy discovery trigger.

Scanopy's own scheduler is unreliable on this fleet, so a systemd timer starts each daemon's discovery at a fixed daily UTC
slot through the API. The job must start only what is due, never double a scan that already ran, never burst after an outage,
and never change anything in Scanopy except starting sessions. A fake in-memory Scanopy and a fixed clock replace the
network and time; nothing here touches a real host.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/files/scanopy-discover/scanopy_discover.py"
)
NOW = dt.datetime(2026, 10, 13, 2, 10, tzinfo=dt.timezone.utc)


@pytest.fixture()
def discover(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("scanopy_discover_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    key_file = tmp_path / "api-key"
    key_file.write_text("test-key\n")
    monkeypatch.setitem(module.CONF, "key_file", str(key_file))
    monkeypatch.setitem(module.CONF, "textfile", str(tmp_path / "scanopy_discover.prom"))
    monkeypatch.setitem(module.CONF, "schedule_file", str(tmp_path / "schedule.json"))
    monkeypatch.setattr(module, "utcnow", lambda: NOW)
    return module


def write_schedule(discover: ModuleType, schedule: dict) -> None:
    Path(discover.CONF["schedule_file"]).write_text(json.dumps(schedule))


def scheduled(did: str, daemon: str, last_run: str | None, enabled: bool = True, cron: str = "0 0 1 * * *") -> dict:
    return {
        "id": did,
        "daemon_id": daemon,
        "run_type": {"type": "Scheduled", "enabled": enabled, "cron_schedule": cron, "last_run": last_run},
    }


class FakeScanopy:
    def __init__(self, daemons: dict[str, str], discoveries: list[dict], conflict: set[str] | None = None) -> None:
        self.daemons = daemons
        self.discoveries = discoveries
        self.conflict = conflict or set()
        self.daemon_extra: dict[str, dict] = {}
        self.starts: list[str] = []
        self.calls: list[tuple[str, str]] = []

    def __call__(self, key: str, method: str, path: str, body: object = None) -> dict:
        assert key == "test-key"
        self.calls.append((method, path.split("?")[0]))
        if method == "GET" and path.startswith("/api/v1/daemons"):
            rows = [{"id": i, "name": n, **self.daemon_extra.get(n, {})} for n, i in self.daemons.items()]
            return {"success": True, "data": rows, "meta": {}}
        if method == "GET" and path.startswith("/api/v1/discovery"):
            return {"success": True, "data": self.discoveries, "meta": {}}
        if method == "POST" and path == "/api/v1/discovery/start-session":
            assert isinstance(body, str)
            if body in self.conflict:
                raise urllib.error.HTTPError("u", 409, "conflict", {}, None)  # type: ignore[arg-type]
            self.starts.append(body)
            return {"success": True, "data": {"session_id": "s"}}
        raise AssertionError(f"unexpected call {method} {path}")


def run(discover: ModuleType, fake: FakeScanopy, monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(discover, "call", fake)
    monkeypatch.setattr(sys, "argv", ["scanopy_discover.py", *argv])
    with pytest.raises(SystemExit) as exit_info:
        discover.main()
    return int(exit_info.value.code)


def metrics(discover: ModuleType) -> dict[str, float]:
    text = Path(discover.CONF["textfile"]).read_text()
    return {line.split()[0]: float(line.split()[1]) for line in text.splitlines() if line and not line.startswith("#")}


def test_a_host_whose_slot_passed_without_a_run_is_started(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "02:00"})
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", "2026-10-12T02:00:05.1Z")])

    assert run(discover, fake, monkeypatch) == 0

    assert fake.starts == ["d-a"]
    assert metrics(discover)["scanopy_discover_started_this_run"] == 1
    assert metrics(discover)["scanopy_discover_last_attempt_success"] == 1


def test_a_host_that_already_ran_since_its_slot_is_skipped(discover, monkeypatch) -> None:
    # Scanopy's own scheduler (or a manual scan) already ran it at 02:00:03 today: do not double the scan.
    write_schedule(discover, {"vm-a": "02:00"})
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", "2026-10-13T02:00:03.9Z")])

    assert run(discover, fake, monkeypatch) == 0

    assert fake.starts == []
    assert metrics(discover)["scanopy_discover_due"] == 0


def test_a_slot_later_today_is_not_due_yet(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "04:30"})
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", "2026-10-12T04:30:05Z")])  # yesterday's slot was served

    assert run(discover, fake, monkeypatch) == 0

    assert fake.starts == []


def test_a_missed_slot_older_than_the_catchup_window_is_not_made_up(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "01:00"})  # slot was 1h10m ago -> inside the 3h window
    write_after = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", "2026-10-11T01:00:00Z")])
    assert run(discover, write_after, monkeypatch) == 0
    assert write_after.starts == ["d-a"]

    write_schedule(discover, {"vm-a": "21:00"})  # slot was 5h10m ago (yesterday) -> outside the window
    stale = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", "2026-10-11T21:00:00Z")])
    assert run(discover, stale, monkeypatch) == 0
    assert stale.starts == []
    assert metrics(discover)["scanopy_discover_oldest_last_run_age_seconds"] > 24 * 3600  # surfaced for the alert


def test_at_most_one_session_is_started_per_run(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "02:00", "vm-b": "02:05", "vm-c": "02:08"})
    fake = FakeScanopy(
        {"vm-a": "da", "vm-b": "db", "vm-c": "dc"},
        [scheduled("d-a", "da", "2026-10-12T02:00:00Z"), scheduled("d-b", "db", "2026-10-12T02:05:00Z"), scheduled("d-c", "dc", "2026-10-12T02:08:00Z")],
    )

    assert run(discover, fake, monkeypatch) == 0

    assert fake.starts == ["d-a"]  # earliest slot first; the others wait for the next 15-minute run
    assert metrics(discover)["scanopy_discover_due"] == 3


def test_a_session_already_running_is_skipped_not_an_error(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "02:00"})
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", None)], conflict={"d-a"})

    assert run(discover, fake, monkeypatch) == 0

    assert metrics(discover)["scanopy_discover_errors"] == 0


def test_an_enabled_definition_wins_over_a_disabled_leftover(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "02:00"})
    fake = FakeScanopy(
        {"vm-a": "da"},
        [scheduled("old", "da", "2026-10-12T11:41:00Z", enabled=False), scheduled("new", "da", "2026-10-12T02:00:00Z")],
    )

    assert run(discover, fake, monkeypatch) == 0

    assert fake.starts == ["new"]


def test_unknown_daemons_and_missing_definitions_are_errors_but_others_still_run(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-gone": "01:50", "vm-nodef": "01:55", "vm-a": "02:00"})
    fake = FakeScanopy({"vm-nodef": "dn", "vm-a": "da"}, [scheduled("d-a", "da", "2026-10-12T02:00:00Z")])

    assert run(discover, fake, monkeypatch) == 1

    assert fake.starts == ["d-a"]
    assert metrics(discover)["scanopy_discover_errors"] == 2
    assert metrics(discover)["scanopy_discover_last_attempt_success"] == 0
    assert "scanopy_discover_last_success_timestamp_seconds" not in metrics(discover)


def test_dry_run_starts_nothing_and_publishes_no_metrics(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "02:00"})
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", "2026-10-12T02:00:00Z")])

    assert run(discover, fake, monkeypatch, "--dry-run") == 0

    assert fake.starts == [] and not Path(discover.CONF["textfile"]).exists()


def test_a_host_that_never_ran_reports_a_finite_age(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "02:00"})
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", None)])

    assert run(discover, fake, monkeypatch) == 0

    assert metrics(discover)["scanopy_discover_oldest_last_run_age_seconds"] == discover.NEVER_RAN_AGE


def test_missing_key_and_bad_schedule_fail_without_calling_scanopy(discover, monkeypatch, tmp_path) -> None:
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", None)])
    write_schedule(discover, {})
    assert run(discover, fake, monkeypatch) == 1  # empty schedule
    write_schedule(discover, {"vm-a": "02:00"})
    monkeypatch.setitem(discover.CONF, "key_file", str(tmp_path / "missing"))
    assert run(discover, fake, monkeypatch) == 1  # no key

    assert fake.calls == [] and fake.starts == []


def test_the_job_only_ever_starts_sessions() -> None:
    source = MODULE_PATH.read_text()

    assert '"PUT"' not in source and '"DELETE"' not in source and "bulk-" not in source
    assert source.count('"POST"') == 1 and "/api/v1/discovery/start-session" in source


def test_a_daemon_missing_from_the_inventory_is_scheduled_from_its_daily_cron(discover, monkeypatch) -> None:
    # The onboarding job gives a new daemon a daily quarter-hour cron in Scanopy; no inventory edit is needed to scan it.
    write_schedule(discover, {"vm-a": "04:00"})
    fake = FakeScanopy(
        {"vm-a": "da", "vm-new": "dn"},
        [scheduled("d-a", "da", "2026-10-12T04:00:00Z"), scheduled("d-new", "dn", None, cron="0 0 2 * * *")],
    )

    assert run(discover, fake, monkeypatch) == 0

    assert fake.starts == ["d-new"]
    assert metrics(discover)["scanopy_discover_targets"] == 2


def test_weekly_or_off_grid_or_disabled_schedules_are_not_adopted(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "04:00"})
    fake = FakeScanopy(
        {"vm-a": "da", "w": "dw", "g": "dg", "x": "dx"},
        [
            scheduled("d-a", "da", "2026-10-12T04:00:00Z"),
            scheduled("d-w", "dw", None, cron="0 0 2 * * 0"),  # Scanopy's default weekly definition
            scheduled("d-g", "dg", None, cron="0 7 2 * * *"),  # minute is not on the 15-minute grid
            scheduled("d-x", "dx", None, enabled=False, cron="0 0 2 * * *"),
        ],
    )

    assert run(discover, fake, monkeypatch) == 0

    assert fake.starts == [] and metrics(discover)["scanopy_discover_targets"] == 1


def test_the_inventory_slot_wins_over_the_cron_stored_in_scanopy(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "09:00"})
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", "2026-10-12T09:00:00Z", cron="0 0 2 * * *")])

    assert run(discover, fake, monkeypatch) == 0

    assert fake.starts == []  # 02:00 would be due (ran yesterday 09:00); the inventory slot 09:00 is not


def test_daemon_liveness_is_published_per_daemon(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "04:00"})
    fake = FakeScanopy({"vm-a": "da", "vm-b": "db"}, [scheduled("d-a", "da", "2026-10-12T04:00:00Z")])
    fake.daemon_extra = {
        "vm-a": {"last_seen": "2026-10-13T02:09:30.123456Z", "is_unreachable": False},
        "vm-b": {"last_seen": "2026-10-13T00:10:00Z", "is_unreachable": True},
    }

    run(discover, fake, monkeypatch)

    m = metrics(discover)
    assert m['scanopy_daemon_last_seen_age_seconds{daemon="vm-a"}'] == 30
    assert m['scanopy_daemon_last_seen_age_seconds{daemon="vm-b"}'] == 2 * 3600
    assert m["scanopy_daemons_total"] == 2 and m["scanopy_daemons_unreachable"] == 1


def test_a_daemon_that_never_checked_in_reports_the_finite_never_age(discover, monkeypatch) -> None:
    write_schedule(discover, {"vm-a": "04:00"})
    fake = FakeScanopy({"vm-a": "da"}, [scheduled("d-a", "da", "2026-10-12T04:00:00Z")])
    fake.daemon_extra = {"vm-a": {"last_seen": None}}

    run(discover, fake, monkeypatch)

    assert metrics(discover)['scanopy_daemon_last_seen_age_seconds{daemon="vm-a"}'] == discover.NEVER_RAN_AGE
