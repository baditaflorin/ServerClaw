from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "gate-status.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_gate_status_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_missing", WRAPPER_PATH)
    payload = module.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_gate_status_wrapper_executes_repo_script_and_returns_json_payload(monkeypatch, tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_present", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "gate_status.py").write_text("# placeholder\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["text"] = kwargs["text"]
        captured["capture_output"] = kwargs["capture_output"]
        captured["check"] = kwargs["check"]
        return subprocess.CompletedProcess(
            command,
            0,
            '{"manifest_path":"/srv/proxmox_florin_server/config/validation-gate.json","enabled_checks":[{"id":"lint"}],"last_run":{"status":"passed"}}\n',
            "",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert captured["cwd"] == repo_root
    assert captured["text"] is True
    assert captured["capture_output"] is True
    assert captured["check"] is False
    assert captured["command"] == [
        "python3",
        str(repo_root / "scripts" / "gate_status.py"),
        "--format",
        "json",
    ]
    assert payload["gate_status"]["manifest_path"].endswith("config/validation-gate.json")
    assert payload["gate_status"]["last_run"] == {"status": "passed"}
    assert payload["returncode"] == 0


def test_gate_status_wrapper_returns_structured_error_when_stdout_is_not_json(
    monkeypatch, tmp_path: Path
) -> None:
    module = load_module("gate_status_windmill_invalid_json", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "gate_status.py").write_text("# placeholder\n", encoding="utf-8")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            "Validation gate manifest: noisy helper output\nEnabled checks: noisy helper output\n",
            "",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "error"
    assert payload["reason"] == "gate status command did not return valid JSON"
    assert payload["returncode"] == 0
    assert "Validation gate manifest" in payload["stdout"]


def test_gate_status_wrapper_returns_structured_error_when_command_fails(monkeypatch, tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_payload_failure", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "gate_status.py").write_text("# placeholder\n", encoding="utf-8")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, "", "boom")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "error"
    assert payload["reason"] == "gate status command failed"
    assert payload["returncode"] == 2
    assert payload["stderr"] == "boom"
