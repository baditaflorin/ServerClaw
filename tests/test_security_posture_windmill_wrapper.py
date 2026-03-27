from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "security-posture-scan.py"
SPEC = importlib.util.spec_from_file_location("security_posture_scan_wrapper", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_wrapper_blocks_when_required_repo_paths_are_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "security_posture_report.py").write_text("", encoding="utf-8")

    result = MODULE.main(repo_path=str(repo_root))

    assert result["status"] == "blocked"
    assert "missing_paths" in result


def test_wrapper_accepts_warn_status_when_report_json_is_present(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "inventory" / "host_vars").mkdir(parents=True)
    (repo_root / "inventory" / "group_vars").mkdir(parents=True)
    (repo_root / "playbooks" / "tasks").mkdir(parents=True)
    (repo_root / "scripts" / "security_posture_report.py").write_text("", encoding="utf-8")
    (repo_root / "inventory" / "host_vars" / "proxmox_florin.yml").write_text("", encoding="utf-8")
    (repo_root / "inventory" / "group_vars" / "all.yml").write_text("", encoding="utf-8")
    (repo_root / "playbooks" / "tasks" / "security-scan.yml").write_text("", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=2, stdout="Receipt: x\nREPORT_JSON={}\n", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)

    result = MODULE.main(repo_path=str(repo_root))

    assert result["status"] == "ok"
    assert result["returncode"] == 2
    assert result["command"].startswith("uv run")


def test_wrapper_rejects_cli_errors_without_report_json(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "inventory" / "host_vars").mkdir(parents=True)
    (repo_root / "inventory" / "group_vars").mkdir(parents=True)
    (repo_root / "playbooks" / "tasks").mkdir(parents=True)
    (repo_root / "scripts" / "security_posture_report.py").write_text("", encoding="utf-8")
    (repo_root / "inventory" / "host_vars" / "proxmox_florin.yml").write_text("", encoding="utf-8")
    (repo_root / "inventory" / "group_vars" / "all.yml").write_text("", encoding="utf-8")
    (repo_root / "playbooks" / "tasks" / "security-scan.yml").write_text("", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=2, stdout="", stderr="security posture error: missing inventory")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)

    result = MODULE.main(repo_path=str(repo_root))

    assert result["status"] == "error"
    assert result["returncode"] == 2
