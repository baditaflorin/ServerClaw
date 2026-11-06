"""standby-ctl: a guest step that runs out of time leaves the guest's own account of itself in the run record.

Why: on 2026-10-31 the daily rehearsal failed with `silent: guest exit 124` and `teardown: guest exit 124` (603 s). The guest's boot had stalled before multi-user.target
(docker.service never finished starting, so every docker command blocked); the record said only "did not finish in time" and the guest's journal of that boot was gone by the
next day, so the cause could not be shown. The controller now runs one bounded diagnostic script in the guest when a step times out and keeps the text in the record.

Reuses the fake hypervisor of test_standby_ctl.py (it speaks the real `qm` command line); a subclass adds the one thing that file cannot do: a guest command that is still
running when the agent's wait ends (the reply then has no `exitcode`).
"""

from __future__ import annotations

import json
import os
import re

import pytest

from tests.test_standby_ctl import SECRET, FakeMachine, make_bundle, run_main, sc  # noqa: F401 - the world fixture is built here


DIAG_TEXT = "uptime: 05:55:15 up 5 min\n--- systemd jobs still queued\n  JOB UNIT           TYPE  STATE\n  118 docker.service start running\n--- unit states\ndocker=activating\n"


class HangingMachine(FakeMachine):
    """`hang`: guest scripts that never finish (qm returns the partial reply without an exit code)."""

    def __init__(self):
        super().__init__()
        self.hang = set()

    def _guest(self, argv, stdin):
        name = re.match(r"# standby-ctl:(\S+)\n", argv[-1]).group(1)
        if name in self.hang and self.status == "running":
            self.scripts.append((name, argv[-1]))
            return 0, json.dumps({"out-data": "partial"}), ""
        return super()._guest(argv, stdin)

    def _default(self, name):
        if name == "diag":
            return DIAG_TEXT
        return super()._default(name)


@pytest.fixture
def hung(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(sc, "DISABLE_FILE", "/etc/standby-ctl/DISABLE")
    return HangingMachine()


def diag_scripts(world):
    return [s for n, s in world.scripts if n == "diag"]


def test_a_silent_step_that_times_out_leaves_the_guest_diagnostics_in_the_record(hung):
    hung.hang = {"silent"}
    code, res = run_main(hung, "rehearse", make_bundle())
    assert code == 5 and not res["ok"] and "guest exit 124" in res["error"]
    assert res["guest_diag"].startswith("after step silent:\n") and "docker.service start running" in res["guest_diag"]
    names = [n for n, _ in hung.scripts]
    assert (
        names.index("silent") < names.index("diag") < names.index("teardown")
    )  # taken before the teardown adds its own wait
    assert hung.status == "stopped" and "link_down=1" in hung.net0  # the run still ends resting
    assert "up" not in hung.link_changes  # and a standby that never got to prove it was silent never got its link


def test_one_diagnostic_per_run_even_when_the_teardown_hangs_too(hung):
    hung.hang = {"silent", "teardown"}
    code, res = run_main(hung, "rehearse", make_bundle())
    assert code == 5 and len(diag_scripts(hung)) == 1
    assert [s["ok"] for s in res["steps"] if s["step"] in ("silent", "teardown")] == [False, False]
    assert hung.status == "stopped" and "link_down=1" in hung.net0 and not res.get("cleanup_failed")


def test_a_wedged_agent_is_recorded_as_such_and_never_replaces_the_failure(hung):
    hung.hang = {"silent", "diag"}
    code, res = run_main(hung, "rehearse", make_bundle())
    assert code == 5 and "silent: guest exit 124" in res["error"]
    assert "unavailable: guest exit 124" in res["guest_diag"]
    assert hung.status == "stopped" and "link_down=1" in hung.net0


def test_the_diagnostic_never_touches_docker_and_bounds_every_command(hung):
    hung.hang = {"silent"}
    run_main(hung, "rehearse", make_bundle())
    (script,) = diag_scripts(hung)
    assert not re.search(
        r"^\s*docker\b|[;|&(]\s*docker\b", script, re.M
    )  # a hung docker is the very case it exists for
    for line in script.splitlines():
        for tool in ("systemctl", "journalctl", "dmesg"):
            if re.search(rf"\b{tool}\b", line):
                assert re.search(rf"timeout \d+ {tool}\b", line), line


def test_nothing_secret_survives_into_the_diagnostic(hung):
    hung.hang = {"silent"}
    hung.out["diag"] = f"dsn=postgres://domainscope_app:{SECRET}@db.example:5432/x\nplain\n"
    code, res = run_main(hung, "rehearse", make_bundle())
    assert SECRET not in json.dumps(res) and "plain" in res["guest_diag"]
    assert SECRET not in json.dumps(hung.state)


def test_a_healthy_rehearsal_and_an_ordinary_step_failure_run_no_diagnostic(hung):
    code, res = run_main(hung, "rehearse", make_bundle())
    assert code == 0 and "guest_diag" not in res and not diag_scripts(hung)
    w2 = HangingMachine()
    w2.fail["images"] = (1, "boom")  # an exit code is an answer: nothing to diagnose
    code, res = run_main(w2, "rehearse", make_bundle())
    assert code == 5 and "guest_diag" not in res and not diag_scripts(w2)


def test_an_activation_that_times_out_in_the_silent_step_also_keeps_the_diagnostic(hung):
    hung.hang = {"silent"}
    code, res = run_main(hung, "activate", make_bundle())
    assert code == 5 and "guest exit 124" in res["error"] and "docker.service start running" in res["guest_diag"]
    assert hung.state[os.path.join(sc.STATE_DIR, "state.json")]["phase"] == "ACTIVATION_FAILED"
    assert "up" not in hung.link_changes
