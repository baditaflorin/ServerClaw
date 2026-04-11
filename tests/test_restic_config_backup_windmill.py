from __future__ import annotations

import importlib.util
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "restic-config-backup.py"
SPEC = importlib.util.spec_from_file_location("restic_config_backup_windmill", SCRIPT_PATH)
restic_config_backup_windmill = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(restic_config_backup_windmill)


def test_extract_report_json_reads_last_report_line() -> None:
    payload = restic_config_backup_windmill.extract_report_json('x\nREPORT_JSON={"summary":{"protected":1}}\n')
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


def test_main_uses_api_gateway_fallback_script_when_worker_checkout_is_incomplete(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "worker-checkout"
    repo_root.mkdir()
    fallback_script = tmp_path / "api-gateway" / "service" / "scripts" / "restic_config_backup.py"
    fallback_catalog = tmp_path / "etc" / "lv3" / "restic-config-backup" / "restic-file-backup-catalog.json"
    fallback_script.parent.mkdir(parents=True)
    fallback_catalog.parent.mkdir(parents=True)
    fallback_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    fallback_catalog.write_text(
        '{"schema_version":"1.0.0","controller_host":{"minio":{"bucket":"restic-config-backup"}},"sources":[]}\n',
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run(command, cwd, text, capture_output, check):
        captured["command"] = command
        captured["cwd"] = cwd
        return types.SimpleNamespace(returncode=0, stdout='REPORT_JSON={"summary":{"protected":1}}\n', stderr="")

    monkeypatch.setattr(restic_config_backup_windmill, "DEFAULT_FALLBACK_SCRIPT_PATH", fallback_script)
    monkeypatch.setattr(restic_config_backup_windmill, "DEFAULT_FALLBACK_CATALOG_PATH", fallback_catalog)
    monkeypatch.setattr(restic_config_backup_windmill.subprocess, "run", fake_run)

    payload = restic_config_backup_windmill.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert captured["command"][1] == str(fallback_script)
    assert str(fallback_catalog) in captured["command"]
    assert captured["cwd"] == repo_root


def test_build_parser_accepts_mode_and_trigger_overrides() -> None:
    args = restic_config_backup_windmill.build_parser().parse_args(
        ["--repo-path", "/tmp/repo", "--mode", "restore-verify", "--triggered-by", "manual"]
    )

    assert args.repo_path == "/tmp/repo"
    assert args.mode == "restore-verify"
    assert args.triggered_by == "manual"
