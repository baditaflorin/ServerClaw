import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("c", pathlib.Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "controller" / "tier0_controller.py")
c = importlib.util.module_from_spec(spec); sys.modules["c"] = c; spec.loader.exec_module(c)


def run(ticks, down=5, up=30):
    s, evs = c.State(), []
    for i, t in enumerate(ticks):
        s, e = c.step(s, t, float(i), down, up)
        evs.append(e)
    return s, evs


def test_classify():
    assert c.classify({"a": "DOWN", "b": "DOWN"}) == "DOWN"
    assert c.classify({"a": "DOWN", "b": "UP"}) == "UP"
    assert c.classify({"a": "DOWN", "b": "UNKNOWN"}) == "UNKNOWN"   # unknown never counts as down
    assert c.classify({"a": "UNKNOWN", "b": "UNKNOWN"}) == "UNKNOWN"
    assert c.classify({}) == "UNKNOWN"


def test_failover_decided_exactly_once_after_n_down_ticks():
    s, evs = run(["DOWN"] * 4)
    assert s.state == "SUSPECT" and not any(evs)
    s, evs = run(["DOWN"] * 12)
    assert s.state == "PRIMARY_DOWN" and sum(e.count("FAILOVER") for e in evs) == 1 and evs[4] == ["FAILOVER"]


def test_blip_resets():
    s, evs = run(["DOWN", "DOWN", "DOWN", "DOWN", "UP", "DOWN", "DOWN", "DOWN", "DOWN"])
    assert s.state == "SUSPECT" and not any(evs)   # 4 + 4 are not 5 in a row


def test_unknown_neither_counts_nor_resets():
    s, evs = run(["DOWN"] * 3 + ["UNKNOWN"] * 10 + ["DOWN"] * 2)
    assert s.state == "PRIMARY_DOWN" and evs[-1] == ["FAILOVER"]
    s, evs = run(["DOWN"] * 3 + ["UNKNOWN"] * 50)
    assert s.state == "SUSPECT" and not any(evs)    # an unusable vantage point never creates a decision


def test_failback_only_after_m_consecutive_up_ticks_once():
    base = ["DOWN"] * 5
    s, evs = run(base + ["UP"] * 29)
    assert s.state == "RECOVERING" and sum(e.count("FAILBACK") for e in evs) == 0
    s, evs = run(base + ["UP"] * 30)
    assert s.state == "NORMAL" and evs[-1] == ["FAILBACK"]
    s, evs = run(base + ["UP"] * 60)
    assert sum(e.count("FAILBACK") for e in evs) == 1


def test_down_during_recovery_does_not_failover_again():
    s, evs = run(["DOWN"] * 5 + ["UP"] * 10 + ["DOWN"] + ["UP"] * 5)
    assert sum(e.count("FAILOVER") for e in evs) == 1 and s.state == "RECOVERING"


def test_up_during_suspect_returns_to_normal():
    s, _ = run(["DOWN", "DOWN", "UP"])
    assert s.state == "NORMAL" and s.down_ticks == 0


def test_step_is_pure():
    s = c.State("SUSPECT", 3, 0, 1.0)
    c.step(s, "DOWN", 2.0)
    assert (s.state, s.down_ticks) == ("SUSPECT", 3)
