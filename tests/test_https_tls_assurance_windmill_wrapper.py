from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "https-tls-assurance.py"
SPEC = importlib.util.spec_from_file_location("https_tls_assurance_wrapper", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_wrapper_blocks_when_script_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = MODULE.main(repo_path=str(repo_root))

    assert result["status"] == "blocked"
    assert "missing" in result["reason"]


def test_wrapper_uses_uv_and_timeout_and_accepts_warn_status(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "https_tls_assurance.py").write_text("", encoding="utf-8")

    def fake_run(command, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="Receipt: x\nREPORT_JSON={}\n", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)

    result = MODULE.main(repo_path=str(repo_root), timeout_seconds=75)

    assert result["status"] == "ok"
    assert result["returncode"] == 1
    assert result["command"].startswith("uv run --with pyyaml python")
    assert "--timeout-seconds 75" in result["command"]


def test_wrapper_rejects_missing_report_json(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "https_tls_assurance.py").write_text("", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=2, stdout="", stderr="https tls assurance error: missing receipt")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)

    result = MODULE.main(repo_path=str(repo_root))

    assert result["status"] == "error"
    assert result["returncode"] == 2
