"""REPLAY of recorded reality through the controller's real state machine (config/0infer/tier0-runner/controller/replay.py).

Data: real Prometheus samples of the public-edge probes (tests/fixtures/tier0_edge_probe_replay.json). The point of this test is not the arithmetic (test_tier0_controller.py has that) but the
claim that justified the design: the rule decides correctly on a REAL outage and stays silent on the things that look like outages but are not."""
import importlib.util
import json
import pathlib
import sys

CTRL = pathlib.Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "controller"
spec = importlib.util.spec_from_file_location("replay", CTRL / "replay.py")
replay = importlib.util.module_from_spec(spec)
sys.modules["replay"] = replay
spec.loader.exec_module(replay)
FIX = json.loads((pathlib.Path(__file__).parent / "fixtures" / "tier0_edge_probe_replay.json").read_text())["windows"]


def decisions(window, mode, down=5, up=30):
    dec, runs = replay.run(FIX[window], mode, down, up)
    return [(t, e) for t, e in dec], runs


def hm(t):
    import time
    return time.strftime("%H:%M", time.gmtime(t))


def test_the_real_2026_10_13_outage_is_decided_once_within_minutes_and_handed_back_once():
    dec, runs = decisions("outage_2026-10-13", "strict")
    fo = [t for t, e in dec if e == "FAILOVER"]
    fb = [t for t, e in dec if e == "FAILBACK"]
    assert len(fo) == 1 and len(fb) == 1                       # exactly one failover and one failback decision for the whole episode
    assert "10:08" <= hm(fo[0]) <= "10:11"                     # the outage began 10:05Z: decided after 5 consecutive down ticks, not before
    assert "11:10" <= hm(fb[0]) <= "11:20"                     # recovered ~10:45Z: handed back only after 30 consecutive up ticks
    assert len(runs) == 2                                      # the 3-minute flap just after recovery was seen ...
    assert fo[0] < runs[1][0]                                  # ... and did NOT cause a second failover decision


def test_a_normal_night_with_the_builder_backup_stop_decides_nothing():
    """CT108's nightly backup takes ci.0exec.com down ~10 minutes at 01:30Z. One failing app must never look like a lost host."""
    assert decisions("nightly_ct108_backup_2026-10-16", "strict")[0] == []
    dec, _ = decisions("nightly_ct108_backup_2026-10-16", "sensitive")
    assert any(e == "FAILOVER" for _, e in dec)                # a rule that fired on ANY failing probe would have failed over in the night: that is why the rule needs ALL of them


def test_one_application_down_for_two_hours_decides_nothing():
    assert decisions("one_app_down_129min_2026-10-12", "strict")[0] == []
    dec, runs = decisions("one_app_down_129min_2026-10-12", "sensitive")
    assert any(e == "FAILOVER" for _, e in dec) and max((b - a) // 60 for a, b in runs) >= 120


def test_slower_rule_still_catches_the_real_outage_and_faster_one_catches_it_sooner():
    f3 = [t for t, e in decisions("outage_2026-10-13", "strict", 3, 15)[0] if e == "FAILOVER"]
    f10 = [t for t, e in decisions("outage_2026-10-13", "strict", 10, 30)[0] if e == "FAILOVER"]
    assert len(f3) == 1 and len(f10) == 1 and f3[0] < f10[0]
