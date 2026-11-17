"""Safety, checkpoints, and reader-pressure gates for incremental CT trim."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "config/0own/ct-names/reclaim/ct-names-reclaim.py"
spec = importlib.util.spec_from_file_location("ct_reclaim", SCRIPT)
reclaim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reclaim)


def reader(**changes):
    values = dict.fromkeys(["disk", "host_memory", "io", "load", "memory"], 0)
    values.update(changes)
    return "ct_names_entries_per_second 100\n" + "".join(
        f'ct_names_reader_paused{{reason="{key}"}} {value}\n' for key, value in values.items()
    )


def test_reader_gate_is_fail_closed():
    assert reclaim.reader_ready(reader())
    assert not reclaim.reader_ready(reader(io=1))
    assert not reclaim.reader_ready(reader().replace('ct_names_reader_paused{reason="disk"} 0\n', ""))
    assert not reclaim.reader_ready(reader().replace("per_second 100", "per_second 0"))
    assert reclaim.pressure("some avg10=9.99 avg60=4 avg300=1 total=0") == 9.99
    with pytest.raises(ValueError):
        reclaim.pressure("full avg10=0")


@pytest.fixture
def environment(monkeypatch, tmp_path):
    monkeypatch.setattr(reclaim, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(reclaim, "METRIC", tmp_path / "textfile" / "ct_names_reclaim.prom")
    psi = tmp_path / "io"
    psi.write_text("some avg10=1.00 avg60=1 avg300=1 total=1\n")
    monkeypatch.setattr(reclaim, "PSI", psi)
    monkeypatch.setattr(reclaim, "identity", lambda: ("uuid-1", reclaim.GROUP_BYTES * 2))
    monkeypatch.setattr(reclaim, "reader_metrics", reader)
    calls = []
    monkeypatch.setattr(reclaim, "trim_group", lambda offset, fd: calls.append(offset) or 0.5)
    return tmp_path, calls


def test_advances_after_success_wraps_and_persists(environment):
    tmp, calls = environment
    reclaim.main()
    reclaim.main()
    state = json.loads((tmp / "state/state.json").read_text())
    assert calls == [0, reclaim.GROUP_BYTES]
    assert state["offset"] == 0 and state["cycles"] == 1
    assert "ct_names_reclaim_cycles 1" in (tmp / "textfile/ct_names_reclaim.prom").read_text()
    assert (tmp / "textfile/ct_names_reclaim.prom").stat().st_mode & 0o777 == 0o644
    assert (tmp / "state/state.json").stat().st_mode & 0o777 == 0o600


def test_high_pressure_and_paused_reader_do_not_advance(environment, monkeypatch):
    tmp, calls = environment
    (tmp / "io").write_text("some avg10=11.00 avg60=1 avg300=1 total=1\n")
    reclaim.main()
    assert calls == []
    assert "ct_names_reclaim_blocked 1" in (tmp / "textfile/ct_names_reclaim.prom").read_text()
    (tmp / "io").write_text("some avg10=1 avg60=1 avg300=1 total=1\n")
    monkeypatch.setattr(reclaim, "reader_metrics", lambda: reader(io=1))
    reclaim.main()
    assert calls == []
    assert json.loads((tmp / "state/state.json").read_text())["offset"] == 0


def test_failure_never_advances_and_is_visible(environment, monkeypatch):
    tmp, _ = environment

    def fail(*_args):
        raise RuntimeError("trim stalled")

    monkeypatch.setattr(reclaim, "trim_group", fail)
    with pytest.raises(RuntimeError):
        reclaim.main()
    assert json.loads((tmp / "state/state.json").read_text())["offset"] == 0
    assert "ct_names_reclaim_error 1" in (tmp / "textfile/ct_names_reclaim.prom").read_text()


def test_changed_disk_rejected_without_resetting_checkpoint(environment, monkeypatch):
    tmp, calls = environment
    reclaim.main()
    before = (tmp / "state/state.json").read_text()
    monkeypatch.setattr(reclaim, "identity", lambda: ("replacement-disk", reclaim.GROUP_BYTES * 2))
    with pytest.raises(ValueError):
        reclaim.main()
    assert (tmp / "state/state.json").read_text() == before
    assert calls == [0]


def test_trim_retains_lock_and_kills_on_pressure(monkeypatch, tmp_path):
    class FakeProcess:
        def __init__(self, *_args, **kwargs):
            assert kwargs["pass_fds"] == (42,)
            self.returncode = None
            self.killed = False

        def poll(self):
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self):
            return self.returncode

    instances = []

    def start(*args, **kwargs):
        proc = FakeProcess(*args, **kwargs)
        instances.append(proc)
        return proc

    monkeypatch.setattr(reclaim.subprocess, "Popen", start)
    psi = tmp_path / "psi"
    psi.write_text("some avg10=45.0 avg60=1 avg300=1 total=1\n")
    monkeypatch.setattr(reclaim, "PSI", psi)
    with pytest.raises(RuntimeError, match="pressure"):
        reclaim.trim_group(0, 42)
    assert instances[0].killed


def test_zvol_metrics_checks_disk_ownership(monkeypatch):
    path = SCRIPT.parent / "ct-names-zvol-metrics.py"
    zspec = importlib.util.spec_from_file_location("ct_zvol", path)
    module = importlib.util.module_from_spec(zspec)
    zspec.loader.exec_module(module)

    def output(cmd, **_kwargs):
        if cmd[0] == "qm":
            return "scsi1: local-zfs:vm-660-disk-1,serial=CTNAMES0,size=1T\n"
        return "500\t1000\n"

    monkeypatch.setattr(module.subprocess, "check_output", output)
    assert module.collect() == (500, 1000)
    monkeypatch.setattr(
        module.subprocess, "check_output", lambda *_args, **_kwargs: "scsi1: local-zfs:other,serial=CTNAMES0\n"
    )
    with pytest.raises(ValueError, match="ownership"):
        module.collect()
