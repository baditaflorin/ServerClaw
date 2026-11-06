"""The controller's app-level probe is measurement only: it must never change the decision rule and never raise."""
import importlib.util
import pathlib
import sys
import urllib.error

SRC = pathlib.Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "controller" / "tier0_controller.py"
spec = importlib.util.spec_from_file_location("t0c_app", SRC)
c = importlib.util.module_from_spec(spec)
sys.modules["t0c_app"] = c
spec.loader.exec_module(c)


class _Resp:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_app_probe_classification(monkeypatch):
    def fake(code):
        def f(req, timeout=0):
            if code >= 400:
                raise urllib.error.HTTPError("u", code, "x", {}, None)
            return _Resp(code)
        return f
    for code, want in ((200, 1), (302, 1), (401, 1), (403, 1), (404, 0), (410, 0), (502, 0), (504, 0)):
        monkeypatch.setattr(c.urllib.request, "urlopen", fake(code))
        assert c.app_probe("x.example") == want, code
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert c.app_probe("x.example") == 0


def test_host_up_apps_down_only_when_tick_up_and_every_target_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "APP_PROM", str(tmp_path / "app.prom"))
    def read(): return (tmp_path / "app.prom").read_text()
    c.write_app_metrics("UP", 1000.0, ["a", "b"], probe=lambda t: 0)
    assert "tier0_controller_host_up_apps_down 1" in read()
    c.write_app_metrics("UP", 1000.0, ["a", "b"], probe=lambda t: 1 if t == "a" else 0)
    assert "tier0_controller_host_up_apps_down 0" in read()          # one healthy app: not an apps-down signal
    c.write_app_metrics("DOWN", 1000.0, ["a", "b"], probe=lambda t: 0)
    assert "tier0_controller_host_up_apps_down 0" in read()          # host down is the existing rule's business
    c.write_app_metrics("UNKNOWN", 1000.0, ["a"], probe=lambda t: 0)
    assert "tier0_controller_host_up_apps_down 0" in read()


def test_probe_failures_never_raise_and_never_touch_the_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "APP_PROM", str(tmp_path / "no" / "such" / "dir" / "app.prom"))
    assert c.write_app_metrics("UP", 1.0, ["a"], probe=lambda t: 1) == {"a": 1}       # unwritable path: swallowed
    def boom(t): raise RuntimeError("probe bug")
    assert c.write_app_metrics("UP", 1.0, ["a"], probe=boom) == {}                  # a raising probe: swallowed
    s0 = c.State()
    s1, ev = c.step(s0, "UP", 1.0)
    assert (s1.state, ev) == ("NORMAL", [])
