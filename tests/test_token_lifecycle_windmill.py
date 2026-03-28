from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(relative_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_audit_token_inventory_prepares_runtime_receipt_directory(monkeypatch, tmp_path: Path) -> None:
    module = load_module("config/windmill/scripts/audit-token-inventory.py", "audit_token_inventory_windmill")
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "token_lifecycle.py").write_text("print('ok')\n", encoding="utf-8")
    receipt_dir = tmp_path / ".local" / "token-lifecycle" / "receipts"
    receipt_dir.mkdir(parents=True)
    original_chmod = module.Path.chmod

    def fake_chmod(self: Path, mode: int) -> None:
        if self == receipt_dir:
            raise PermissionError("simulated shared-runtime chmod refusal")
        original_chmod(self, mode)

    def fake_run(command, *, cwd, text, capture_output, check):
        assert cwd == tmp_path
        assert "--receipt-dir" in command
        observed_dir = Path(command[command.index("--receipt-dir") + 1])
        assert observed_dir == receipt_dir
        assert observed_dir.is_dir()
        assert (observed_dir / ".windmill-write-probe").exists() is False
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"status":"ok","receipt_path":".local/token-lifecycle/receipts/demo.json"}\n',
            stderr="",
        )

    monkeypatch.setattr(module.Path, "chmod", fake_chmod)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(tmp_path), dry_run=True)

    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "ok"


def test_token_exposure_response_prepares_runtime_incident_directory(monkeypatch, tmp_path: Path) -> None:
    module = load_module("config/windmill/scripts/token-exposure-response.py", "token_exposure_response_windmill")
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "token_lifecycle.py").write_text("print('ok')\n", encoding="utf-8")
    incident_dir = tmp_path / ".local" / "token-lifecycle" / "incidents"
    incident_dir.mkdir(parents=True)
    original_chmod = module.Path.chmod

    def fake_chmod(self: Path, mode: int) -> None:
        if self == incident_dir:
            raise PermissionError("simulated shared-runtime chmod refusal")
        original_chmod(self, mode)

    def fake_run(command, *, cwd, text, capture_output, check):
        assert cwd == tmp_path
        assert "--incident-dir" in command
        observed_dir = Path(command[command.index("--incident-dir") + 1])
        assert observed_dir == incident_dir
        assert observed_dir.is_dir()
        assert (observed_dir / ".windmill-write-probe").exists() is False
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"status":"ok","incident_path":".local/token-lifecycle/incidents/demo.json"}\n',
            stderr="",
        )

    monkeypatch.setattr(module.Path, "chmod", fake_chmod)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(token_id="token-123", repo_path=str(tmp_path), dry_run=True)

    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "ok"
