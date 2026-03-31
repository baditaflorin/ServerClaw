from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "restic-config-backup.py"
SPEC = importlib.util.spec_from_file_location("restic_config_backup_windmill", SCRIPT_PATH)
restic_config_backup_windmill = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(restic_config_backup_windmill)


def test_extract_report_json_reads_last_report_line() -> None:
    payload = restic_config_backup_windmill.extract_report_json("x\nREPORT_JSON={\"summary\":{\"protected\":1}}\n")
    assert payload == {"summary": {"protected": 1}}


def test_build_command_includes_mode_and_live_apply_flag() -> None:
    command = restic_config_backup_windmill.build_command(
        Path("/srv/proxmox_florin_server"),
        mode="restore-verify",
        triggered_by="windmill-monthly-restore-verify",
        live_apply_trigger=True,
    )

    assert "--mode" in command
    assert "restore-verify" in command
    assert "--live-apply-trigger" in command


def test_main_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    payload = restic_config_backup_windmill.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_build_parser_accepts_mode_and_trigger_overrides() -> None:
    args = restic_config_backup_windmill.build_parser().parse_args(
        ["--repo-path", "/tmp/repo", "--mode", "restore-verify", "--triggered-by", "manual"]
    )

    assert args.repo_path == "/tmp/repo"
    assert args.mode == "restore-verify"
    assert args.triggered_by == "manual"
