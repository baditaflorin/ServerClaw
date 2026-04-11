from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "backup-coverage-ledger.py"
SPEC = importlib.util.spec_from_file_location("backup_coverage_ledger_windmill", SCRIPT_PATH)
backup_coverage_ledger_windmill = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(backup_coverage_ledger_windmill)


def test_extract_report_json_reads_last_report_line() -> None:
    payload = backup_coverage_ledger_windmill.extract_report_json('x\nREPORT_JSON={"summary":{"uncovered":1}}\n')
    assert payload == {"summary": {"uncovered": 1}}


def test_main_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    payload = backup_coverage_ledger_windmill.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_main_runs_coverage_script(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "backup_coverage_ledger.py").write_text("print('placeholder')\n", encoding="utf-8")

    class Result:
        returncode = 0
        stdout = 'REPORT_JSON={"summary":{"protected":6,"uncovered":1}}\n'
        stderr = ""

    monkeypatch.setattr(backup_coverage_ledger_windmill.subprocess, "run", lambda *args, **kwargs: Result())

    payload = backup_coverage_ledger_windmill.main(repo_path=str(repo_root), strict=True)

    assert payload["status"] == "ok"
    assert payload["summary"]["protected"] == 6
    assert payload["summary"]["uncovered"] == 1


def test_build_parser_accepts_local_repo_overrides() -> None:
    args = backup_coverage_ledger_windmill.build_parser().parse_args(
        ["--repo-path", "/tmp/repo", "--strict", "--no-write-receipt"]
    )

    assert args.repo_path == "/tmp/repo"
    assert args.strict is True
    assert args.no_write_receipt is True
