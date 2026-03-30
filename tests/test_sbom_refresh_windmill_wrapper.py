from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "sbom-refresh.py"
SPEC = importlib.util.spec_from_file_location("sbom_refresh_wrapper", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_wrapper_blocks_when_required_repo_paths_are_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "sbom_refresh.py").write_text("", encoding="utf-8")

    result = MODULE.main(repo_path=str(repo_root))

    assert result["status"] == "blocked"
    assert "missing_paths" in result


def test_wrapper_accepts_success_with_report_json(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "receipts" / "sbom").mkdir(parents=True)
    (repo_root / "receipts" / "cve").mkdir(parents=True)
    (repo_root / "scripts" / "sbom_refresh.py").write_text("", encoding="utf-8")
    (repo_root / "config" / "image-catalog.json").write_text("{}", encoding="utf-8")
    (repo_root / "config" / "sbom-scanner.json").write_text("{}", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="Scanned 1 managed images\nREPORT_JSON={}\n", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)

    result = MODULE.main(repo_path=str(repo_root))

    assert result["status"] == "ok"
    assert result["returncode"] == 0
    assert result["command"].startswith("uv run")
