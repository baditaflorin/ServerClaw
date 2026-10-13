"""Behaviour tests for the automatic Scanopy onboarding job.

The job lists the running guests of each hypervisor over a forced-command SSH key, compares them with the daemons Scanopy
knows, and installs the daemon in guests that stay uncovered. A fake in-memory Scanopy, a scripted SSH layer and a fixed clock
replace the network, the hypervisors and time; nothing here touches a real host.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/files/scanopy-onboard/scanopy_onboard.py"
)
SECRET = "daemon-key-s3cret-0123456789"
FLEET = {"name": "0mcp", "ssh": "root@10.10.10.1", "port": 22, "relay_url": "http://10.10.10.1:60072"}
FLEET2 = {"name": "0own", "ssh": "root@203.0.113.14", "port": 22, "relay_url": "http://10.60.10.1:60072"}


@pytest.fixture()
def onboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("scanopy_onboard_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    (tmp_path / "api-key").write_text("test-key\n")
    monkeypatch.setitem(module.CONF, "key_file", str(tmp_path / "api-key"))
    monkeypatch.setitem(module.CONF, "fleets_file", str(tmp_path / "fleets.json"))
    monkeypatch.setitem(module.CONF, "schedule_file", str(tmp_path / "schedule.json"))
    monkeypatch.setitem(module.CONF, "state_file", str(tmp_path / "state" / "state.json"))
    monkeypatch.setitem(module.CONF, "textfile", str(tmp_path / "scanopy_onboard.prom"))
    monkeypatch.setitem(module.CONF, "wait_seconds", 30)
    clock = {"t": 1_800_000_000.0}
    monkeypatch.setattr(module, "now_ts", lambda: clock["t"])
    monkeypatch.setattr(module, "sleep", lambda seconds: clock.__setitem__("t", clock["t"] + seconds))
    module.clock = clock  # type: ignore[attr-defined]
    return module


def write_config(onboard: ModuleType, fleets=None, exclude=None) -> None:
    Path(onboard.CONF["fleets_file"]).write_text(json.dumps({
        "site_id": "site-1", "docker_credential_id": "docker-cred", "exclude": exclude or [], "fleets": fleets or [FLEET]}))


def guest(kind="vm", gid=200, name="new-guest", macs=None, ips=None, manageable=True) -> dict:
    return {"kind": kind, "id": gid, "name": name, "macs": macs if macs is not None else [f"bc:24:11:00:00:{gid % 256:02x}"],
            "ips": ips if ips is not None else [f"10.10.10.{gid % 250}"], "manageable": manageable}


class FakeScanopy:
    """In-memory Scanopy: daemons, hosts, discoveries, provisioning, and the two writes the job makes."""

    def __init__(self) -> None:
        self.daemons: list[dict] = []
        self.hosts: list[dict] = []
        self.discoveries: list[dict] = []
        self.provisioned: list[dict] = []
        self.puts: list[tuple[str, dict]] = []
        self.checkin = True  # whether a provisioned daemon registers after install

    def add_daemon(self, name: str, host_id: str, ips=None, macs=None, version="0.17.22") -> None:
        self.daemons.append({"id": f"d-{name}", "name": name, "host_id": host_id, "last_seen": "2026-10-13T08:00:00Z", "version": version})
        self.hosts.append({"id": host_id, "name": name, "hidden": False, "tags": [], "updated_at": "t0", "credential_assignments": [],
                           "ip_addresses": [{"ip_address": ip, "mac_address": None} for ip in (ips or [])]
                           + [{"ip_address": "192.0.2.1", "mac_address": m} for m in (macs or [])]})

    def add_schedule(self, daemon: str, cron: str, enabled=True) -> None:
        self.discoveries.append({"id": f"s-{daemon}", "daemon_id": f"d-{daemon}", "run_type": {
            "type": "Scheduled", "enabled": enabled, "cron_schedule": cron, "timezone": None, "last_run": None}})

    def register(self, name: str) -> None:
        self.add_daemon(name, f"h-{name}")
        self.add_schedule(name, "0 0 3 * * 0")  # Scanopy's default weekly definition appears with the daemon

    def __call__(self, key: str, method: str, path: str, body: object = None) -> dict:
        assert key == "test-key"
        base = path.split("?")[0]
        ok = lambda data: {"success": True, "data": data, "meta": {}}  # noqa: E731
        if method == "GET" and base == "/api/v1/daemons":
            return ok(self.daemons)
        if method == "GET" and base == "/api/v1/hosts":
            return ok(self.hosts)
        if method == "GET" and base == "/api/v1/discovery":
            return ok(self.discoveries)
        if method == "GET" and base.startswith("/api/v1/hosts/"):
            return ok(next(h for h in self.hosts if h["id"] == base.rsplit("/", 1)[1]))
        if method == "POST" and base == "/api/v1/daemons/provision":
            self.provisioned.append(body)
            return ok({"daemon_api_key": {"key": SECRET}})
        if method == "PUT":
            self.puts.append((base, body))
            return ok(body)
        raise AssertionError(f"unexpected call {method} {path}")


class FakeHypervisors:
    """Scripted SSH layer: `list` answers per fleet; `install` answers with a configurable guest output."""

    def __init__(self, scanopy: FakeScanopy, guests: dict[str, list[dict]]) -> None:
        self.scanopy = scanopy
        self.guests = guests
        self.installs: list[tuple[str, str, str | None]] = []
        self.install_output = "RESULT active=yes docker=no\n"
        self.install_rc = 0
        self.down: set[str] = set()

    def __call__(self, fleet: dict, remote_cmd: str, stdin: str | None = None, timeout: int | None = None):
        if fleet["name"] in self.down:
            return 255, "", "ssh: connect to host: Connection timed out"
        if remote_cmd == "list":
            return 0, json.dumps({"wrapper_version": 1, "hostname": fleet["name"], "guests": self.guests.get(fleet["name"], [])}), ""
        assert remote_cmd.startswith("install ")
        self.installs.append((fleet["name"], remote_cmd, stdin))
        name = remote_cmd.split()[4]
        if self.install_rc == 0 and "active=yes" in self.install_output and self.scanopy.checkin:
            self.scanopy.register(name)
        return self.install_rc, self.install_output, ""


def run(onboard: ModuleType, monkeypatch: pytest.MonkeyPatch, scanopy: FakeScanopy, hv: FakeHypervisors, *argv: str) -> int:
    monkeypatch.setattr(onboard, "call", scanopy)
    monkeypatch.setattr(onboard, "ssh", hv)
    monkeypatch.setattr(sys, "argv", ["scanopy_onboard.py", *argv])
    with pytest.raises(SystemExit) as exit_info:
        onboard.main()
    return int(exit_info.value.code)


def metrics(onboard: ModuleType) -> dict[str, float]:
    text = Path(onboard.CONF["textfile"]).read_text()
    return {line.split()[0]: float(line.split()[1]) for line in text.splitlines() if line and not line.startswith("#")}


def state(onboard: ModuleType) -> dict:
    return json.loads(Path(onboard.CONF["state_file"]).read_text())


def test_covered_guests_are_left_alone_by_name_mac_or_unique_ip(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    scanopy.add_daemon("vm-0mcp-200-by-name", "h1")
    scanopy.add_daemon("elsewhere-a", "h2", macs=["bc:24:11:00:00:c9"])
    scanopy.add_daemon("elsewhere-b", "h3", ips=["10.10.10.7"])
    scanopy.add_daemon("vm-0mcp-artifact-cache", "h4")
    hv = FakeHypervisors(scanopy, {"0mcp": [
        guest(gid=200, name="by-name"), guest(gid=201, name="by-mac", macs=["BC:24:11:00:00:C9"]),
        guest(gid=202, name="by-ip", ips=["10.10.10.7"], macs=["bc:24:11:ff:ff:01"]),
        guest(gid=180, name="artifact-cache-lv3"),  # daemon named after the guest without the -lv3 suffix
    ]})

    assert run(onboard, monkeypatch, scanopy, hv) == 0

    assert hv.installs == [] and metrics(onboard)["scanopy_onboard_guests_uncovered"] == 0


def test_an_ip_shared_by_two_daemon_hosts_does_not_count_as_coverage(onboard, monkeypatch) -> None:
    # 10.10.10.x exists in two fleets and Docker bridges repeat everywhere: only an address with a single owner proves anything.
    write_config(onboard)
    scanopy = FakeScanopy()
    scanopy.add_daemon("a", "h1", ips=["10.10.10.9"])
    scanopy.add_daemon("b", "h2", ips=["10.10.10.9"])
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=209, name="ambiguous", ips=["10.10.10.9"], macs=["bc:24:11:aa:aa:aa"])]})

    run(onboard, monkeypatch, scanopy, hv)

    assert metrics(onboard)["scanopy_onboard_guests_uncovered"] == 1


def test_a_guest_is_onboarded_on_its_second_uncovered_run_and_finished_in_scanopy(onboard, monkeypatch) -> None:
    write_config(onboard)
    Path(onboard.CONF["schedule_file"]).write_text(json.dumps({"x": "12:00", "y": "12:15"}))
    scanopy = FakeScanopy()
    scanopy.add_daemon("old", "h-old")
    scanopy.add_schedule("old", "0 30 12 * * *")
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=300, name="Fresh_VM")]})
    hv.install_output = "RESULT active=yes docker=yes\n"

    assert run(onboard, monkeypatch, scanopy, hv) == 0  # first sighting: wait, in case the guest is still being provisioned
    assert hv.installs == [] and state(onboard)["0mcp:vm:300"]["runs"] == 1

    assert run(onboard, monkeypatch, scanopy, hv) == 0
    (fleet_name, command, stdin), = hv.installs
    assert (fleet_name, command) == ("0mcp", "install vm 300 http://10.10.10.1:60072 vm-0mcp-300-Fresh_VM 0.17.22")
    assert stdin == SECRET + "\n"  # the daemon key goes over stdin only, never in the command line
    assert scanopy.provisioned == [{"name": "vm-0mcp-300-Fresh_VM", "site_id": "site-1", "mode": "daemon_poll"}]
    # Slots 12:00, 12:15 (inventory) and 12:30 (Scanopy cron) are taken, so the new daemon gets the next free quarter hour.
    path, body = next((p, b) for p, b in scanopy.puts if p.startswith("/api/v1/discovery/"))
    assert path == "/api/v1/discovery/s-vm-0mcp-300-Fresh_VM" and body["run_type"]["cron_schedule"] == "0 45 12 * * *"
    assert body["run_type"]["enabled"] is True
    host_put = next(b for p, b in scanopy.puts if p.startswith("/api/v1/hosts/"))
    assert host_put["credential_assignments"] == [{"credential_id": "docker-cred", "ip_address_ids": None}]
    assert "0mcp:vm:300" not in state(onboard)
    assert metrics(onboard)["scanopy_onboard_installs_this_run"] == 1 and metrics(onboard)["scanopy_onboard_guests_uncovered"] == 0


def test_no_docker_credential_is_attached_to_a_guest_without_docker(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=301, name="plain")]})

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)

    assert len(hv.installs) == 1 and not any(p.startswith("/api/v1/hosts/") for p, _ in scanopy.puts)


def test_a_vm_whose_guest_agent_is_silent_is_reported_but_never_touched(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=302, name="no-agent", manageable=False)]})

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)

    assert hv.installs == [] and scanopy.provisioned == []
    assert metrics(onboard)["scanopy_onboard_guests_unmanageable"] == 1


def test_a_failing_install_backs_off_and_is_retried_later(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=303, name="broken")]})
    hv.install_rc, hv.install_output = 6, "ERR install failed: no space left\n"

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)  # fails
    assert len(hv.installs) == 1
    st = state(onboard)["0mcp:vm:303"]
    assert st["fails"] == 1 and "no space left" in st["last_error"] and st["next_try"] == onboard.clock["t"] + 1800
    assert metrics(onboard)["scanopy_onboard_install_failures"] == 1

    onboard.clock["t"] += 600
    run(onboard, monkeypatch, scanopy, hv)
    assert len(hv.installs) == 1  # still backing off

    onboard.clock["t"] += 1300
    run(onboard, monkeypatch, scanopy, hv)
    assert len(hv.installs) == 2 and state(onboard)["0mcp:vm:303"]["fails"] == 2  # backoff doubles: 3600 s


def test_a_guest_that_already_runs_an_active_daemon_is_not_reinstalled(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=304, name="has-service")]})
    hv.install_output = "RESULT skipped=already-active\n"

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)

    assert "already active" in state(onboard)["0mcp:vm:304"]["last_error"]
    assert metrics(onboard)["scanopy_onboard_guests_uncovered"] == 1


def test_a_daemon_that_never_checks_in_is_a_failure_with_a_relay_hint(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    scanopy.checkin = False
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=305, name="silent")]})

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)

    assert "did not check in" in state(onboard)["0mcp:vm:305"]["last_error"]


def test_at_most_max_installs_per_run_and_the_rest_wait(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=310 + i, name=f"g{i}") for i in range(4)]})

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)
    assert len(hv.installs) == 2
    run(onboard, monkeypatch, scanopy, hv)
    assert len(hv.installs) == 4


def test_a_fleet_that_cannot_be_listed_fails_the_run_and_withholds_the_success_timestamp(onboard, monkeypatch) -> None:
    write_config(onboard, fleets=[FLEET, FLEET2])
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [], "0own": []})
    hv.down.add("0own")

    assert run(onboard, monkeypatch, scanopy, hv) == 1

    m = metrics(onboard)
    assert m['scanopy_onboard_fleet_list_ok{hypervisor="0mcp"}'] == 1 and m['scanopy_onboard_fleet_list_ok{hypervisor="0own"}'] == 0
    assert "scanopy_onboard_last_success_timestamp_seconds" not in m


def test_a_single_ssh_timeout_while_listing_is_retried_once(onboard, monkeypatch) -> None:
    write_config(onboard, fleets=[FLEET, FLEET2])
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [], "0own": []})
    real = hv.__call__
    calls = {"0own": 0}

    def flaky(fleet, remote_cmd, stdin=None, timeout=None):
        if fleet["name"] == "0own" and remote_cmd == "list":
            calls["0own"] += 1
            if calls["0own"] == 1:
                raise subprocess.TimeoutExpired("ssh", 40)
        return real(fleet, remote_cmd, stdin, timeout)

    monkeypatch.setattr(onboard, "call", scanopy)
    monkeypatch.setattr(onboard, "ssh", flaky)
    monkeypatch.setattr(sys, "argv", ["scanopy_onboard.py"])
    with pytest.raises(SystemExit) as exit_info:
        onboard.main()

    assert exit_info.value.code == 0 and calls["0own"] == 2
    assert metrics(onboard)['scanopy_onboard_fleet_list_ok{hypervisor="0own"}'] == 1


def test_a_fleet_that_stays_down_after_the_retry_still_fails_the_run(onboard, monkeypatch) -> None:
    write_config(onboard, fleets=[FLEET, FLEET2])
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [], "0own": []})
    hv.down.add("0own")

    assert run(onboard, monkeypatch, scanopy, hv) == 1


def test_failure_state_is_forgotten_when_the_guest_becomes_covered_or_disappears(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=320, name="flaky")]})
    hv.install_rc, hv.install_output = 6, "ERR install failed\n"
    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)
    assert "0mcp:vm:320" in state(onboard)

    hv.guests["0mcp"] = []  # the guest was stopped or removed
    run(onboard, monkeypatch, scanopy, hv)

    assert state(onboard) == {} and metrics(onboard)["scanopy_onboard_install_failures"] == 0


def test_excluded_guests_are_ignored(onboard, monkeypatch) -> None:
    write_config(onboard, exclude=["0mcp:vm:330"])
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=330, name="template-like")]})

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)

    assert hv.installs == [] and metrics(onboard)["scanopy_onboard_guests_uncovered"] == 0


def test_dry_run_changes_nothing_and_publishes_nothing(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=340, name="dry")]})
    monkeypatch.setitem(onboard.CONF, "min_runs", 1)

    assert run(onboard, monkeypatch, scanopy, hv, "--dry-run") == 0

    assert hv.installs == [] and scanopy.provisioned == [] and scanopy.puts == []
    assert not Path(onboard.CONF["state_file"]).exists() and not Path(onboard.CONF["textfile"]).exists()


def test_the_daemon_key_never_appears_in_the_log(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=350, name="quiet")]})
    lines: list[str] = []
    monkeypatch.setattr(onboard, "log", lines.append)

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)

    assert any(line.startswith("ONBOARDED") for line in lines)
    assert not any(SECRET in line for line in lines)


def test_a_daemon_record_that_never_checked_in_is_not_coverage_and_is_re_provisioned(onboard, monkeypatch) -> None:
    write_config(onboard)
    scanopy = FakeScanopy()
    scanopy.daemons.append({"id": "d-old", "name": "vm-0mcp-360-again", "host_id": None, "last_seen": None, "version": "0.17.22"})
    hv = FakeHypervisors(scanopy, {"0mcp": [guest(gid=360, name="again")]})

    run(onboard, monkeypatch, scanopy, hv)
    run(onboard, monkeypatch, scanopy, hv)

    assert scanopy.provisioned == [{"daemon_id": "d-old"}]


def test_free_slot_picks_the_first_free_quarter_hour_wraps_and_balances_when_full(onboard) -> None:
    assert onboard.free_slot({}, "12:00") == "12:00"
    assert onboard.free_slot({12 * 60: 1, 12 * 60 + 15: 1}, "12:00") == "12:30"
    # Slots before the start hour are only used after the evening ones (the day wraps at midnight).
    taken = {m: 1 for m in range(12 * 60, 24 * 60, 15)}
    assert onboard.free_slot(taken, "12:00") == "00:00"
    everything = {m: 1 for m in range(0, 1440, 15)}
    everything[18 * 60] = 0
    assert onboard.free_slot(everything, "12:00") == "18:00"


def test_the_version_follows_the_fleet_and_a_missing_or_odd_version_falls_back_to_latest(onboard) -> None:
    assert onboard.daemon_version([{"version": "0.17.22"}, {"version": "0.17.22"}, {"version": "0.17.21"}]) == "0.17.22"
    assert onboard.daemon_version([{"version": None}, {"version": "dev-build"}, {}]) == "latest"


def test_missing_key_or_config_fails_without_calling_anything(onboard, monkeypatch, tmp_path) -> None:
    scanopy = FakeScanopy()
    hv = FakeHypervisors(scanopy, {})
    assert run(onboard, monkeypatch, scanopy, hv) == 1  # no fleets.json yet
    write_config(onboard)
    monkeypatch.setitem(onboard.CONF, "key_file", str(tmp_path / "missing"))
    assert run(onboard, monkeypatch, scanopy, hv) == 1
    assert hv.installs == [] and scanopy.provisioned == []
