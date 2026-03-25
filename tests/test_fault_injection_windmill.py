from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "fault-injection.py"
SPEC = importlib.util.spec_from_file_location("fault_injection_windmill", SCRIPT_PATH)
fault_injection_windmill = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(fault_injection_windmill)


def test_main_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    payload = fault_injection_windmill.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_main_executes_fault_injection_script(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "fault_injection.py").write_text("print('placeholder')\n", encoding="utf-8")

    class Result:
        returncode = 0
        stdout = json.dumps({"status": "passed", "scenario_count": 1})
        stderr = ""

    monkeypatch.setattr(fault_injection_windmill.subprocess, "run", lambda *args, **kwargs: Result())

    payload = fault_injection_windmill.main(
        repo_path=str(repo_root),
        scenario_names="fault:keycloak-unavailable",
        schedule_guard="first_sunday",
        dry_run=True,
    )

    assert payload["status"] == "passed"
    assert payload["scenario_count"] == 1
