from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_SYNC_PATH = REPO_ROOT / "scripts" / "sync_windmill_seed_scripts.py"
SCHEDULES_SYNC_PATH = REPO_ROOT / "scripts" / "sync_windmill_seed_schedules.py"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_retire_script_deletes_only_an_explicit_existing_path(monkeypatch) -> None:
    module = load_module(SCRIPTS_SYNC_PATH, "windmill_seed_script_retirement")
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(module, "get_script", lambda **_kwargs: (200, {"path": "f/lv3/legacy"}))
    monkeypatch.setattr(module, "delete_script", lambda **kwargs: calls.append(("delete", kwargs["script_path"])))
    monkeypatch.setattr(module, "wait_for_absent", lambda **kwargs: calls.append(("wait", kwargs["script_path"])))

    assert module.retire_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="test-token",
        script_path="f/lv3/legacy",
        settle_interval_s=0.1,
    ) == {"path": "f/lv3/legacy", "status": "retired"}
    assert calls == [("delete", "f/lv3/legacy"), ("wait", "f/lv3/legacy")]


def test_retire_schedule_proves_the_explicit_legacy_schedule_is_absent(monkeypatch) -> None:
    module = load_module(SCHEDULES_SYNC_PATH, "windmill_seed_schedule_retirement")
    present = iter([True, False])
    calls: list[tuple[str, str, str]] = []

    monkeypatch.setattr(module, "schedule_exists", lambda **_kwargs: next(present))

    def fake_request(**kwargs):
        calls.append((kwargs["method"], kwargs["path"], kwargs["workspace"]))
        return 204, ""

    monkeypatch.setattr(module, "request_json_or_text", fake_request)

    assert module.retire_schedule(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="test-token",
        schedule_path="f/lv3/legacy_daily",
        timeout_s=2,
    ) == {"path": "f/lv3/legacy_daily", "status": "retired"}
    assert calls == [("DELETE", "schedules/delete/f%2Flv3%2Flegacy_daily", "lv3")]
