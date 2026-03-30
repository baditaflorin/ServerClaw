from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "atlas-drift-check.py"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, WRAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("atlas_drift_missing")
    payload = module.main(repo_path=str(tmp_path / "missing"))

    assert payload["status"] == "blocked"


def test_wrapper_executes_repo_script_and_parses_clean_json(monkeypatch, tmp_path: Path) -> None:
    module = load_module("atlas_drift_present")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"status": "clean", "drift_count": 0}),
            "",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert captured["cwd"] == repo_root
    assert "scripts/atlas_schema.py" in captured["command"]
    assert payload["report"] == {"status": "clean", "drift_count": 0}


def test_wrapper_surfaces_drift_without_treating_it_as_runner_error(monkeypatch, tmp_path: Path) -> None:
    module = load_module("atlas_drift_detected")
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "atlas_schema.py").write_text("# placeholder\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo_root / "scripts" / "run_python_with_packages.sh").chmod(0o755)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            2,
            json.dumps({"status": "drift_detected", "drift_count": 2}),
            "",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "drift"
    assert payload["report"]["drift_count"] == 2
