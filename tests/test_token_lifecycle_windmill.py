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

    def fake_run(command, *, cwd, text, capture_output, check):
        assert cwd == tmp_path
        assert "--receipt-dir" in command
        receipt_dir = Path(command[command.index("--receipt-dir") + 1])
        assert receipt_dir == tmp_path / "receipts" / "token-lifecycle"
        assert receipt_dir.is_dir()
        assert oct(receipt_dir.stat().st_mode & 0o7777) == "0o1777"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"status":"ok","receipt_path":"receipts/token-lifecycle/demo.json"}\n',
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(tmp_path), dry_run=True)

    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "ok"


def test_token_exposure_response_prepares_runtime_incident_directory(monkeypatch, tmp_path: Path) -> None:
    module = load_module("config/windmill/scripts/token-exposure-response.py", "token_exposure_response_windmill")
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "token_lifecycle.py").write_text("print('ok')\n", encoding="utf-8")

    def fake_run(command, *, cwd, text, capture_output, check):
        assert cwd == tmp_path
        assert "--incident-dir" in command
        incident_dir = Path(command[command.index("--incident-dir") + 1])
        assert incident_dir == tmp_path / "receipts" / "security-incidents"
        assert incident_dir.is_dir()
        assert oct(incident_dir.stat().st_mode & 0o7777) == "0o1777"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"status":"ok","incident_path":"receipts/security-incidents/demo.json"}\n',
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(token_id="token-123", repo_path=str(tmp_path), dry_run=True)

    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "ok"
