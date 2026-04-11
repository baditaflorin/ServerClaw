from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "restore-verification.py"
SPEC = importlib.util.spec_from_file_location("restore_verification_windmill", SCRIPT_PATH)
restore_verification_windmill = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(restore_verification_windmill)


def test_extract_report_json_reads_last_report_line() -> None:
    payload = restore_verification_windmill.extract_report_json('x\nREPORT_JSON={"overall":"pass"}\n')
    assert payload == {"overall": "pass"}


def test_main_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    payload = restore_verification_windmill.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_main_runs_restore_script(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "restore_verification.py").write_text("print('placeholder')\n")

    class Result:
        returncode = 0
        stdout = 'REPORT_JSON={"overall":"pass","summary":{"summary":"ok"}}\n'
        stderr = ""

    monkeypatch.setattr(restore_verification_windmill.subprocess, "run", lambda *args, **kwargs: Result())

    payload = restore_verification_windmill.main(repo_path=str(repo_root), publish_nats=False)

    assert payload["status"] == "ok"
    assert payload["report"]["overall"] == "pass"
