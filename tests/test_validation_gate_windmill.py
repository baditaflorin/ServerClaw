from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess


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


def test_gate_status_wrapper_reads_repo_status_payload(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_present", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir()
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)
    (repo_root / ".local" / "validation-gate").mkdir(parents=True)
    (repo_root / "scripts" / "gate_status.py").write_text(
        """
def build_status_payload(*, manifest_path, last_run_path, remote_validate_run_path, post_merge_run_path, bypass_dir):
    return {
        "manifest_path": str(manifest_path),
        "enabled_checks": [],
        "last_run": {"status": "passed"},
        "remote_validate_run": {"status": "passed"},
        "post_merge_run": None,
        "latest_bypass": None,
        "bypass_dir": str(bypass_dir),
    }
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["manifest_path"].endswith("config/validation-gate.json")
    assert payload["gate_status"]["last_run"] == {"status": "passed"}
    assert payload["gate_status"]["waiver_summary"]["totals"]["all_receipts"] == 0
    assert payload["gate_status"]["waiver_summary"]["release_blockers"] == []


def test_gate_status_wrapper_adds_scripts_dir_to_python_path(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_import_path", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "gate_bypass_waivers.py").write_text(
        """
def summarize_receipts(*, directory):
    return {
        "totals": {"all_receipts": 2, "legacy_receipts": 0, "compliant_receipts": 2, "open_waivers": 1, "expired_waivers": 0, "invalid_receipts": 0},
        "latest_receipt": {"path": str(directory / "latest.json")},
        "open_waivers": [{"path": str(directory / "open.json")}],
        "expiring_soon": [],
        "warnings": [],
        "release_blockers": [],
        "invalid_receipts": [],
    }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "scripts" / "gate_status.py").write_text(
        """
import gate_bypass_waivers

def build_status_payload(*, manifest_path, last_run_path, post_merge_run_path, bypass_dir):
    return {
        "manifest_path": str(manifest_path),
        "waiver_summary": gate_bypass_waivers.summarize_receipts(directory=bypass_dir),
    }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["waiver_summary"]["totals"]["all_receipts"] == 2
    assert payload["gate_status"]["waiver_summary"]["open_waivers"] == [
        {"path": str(repo_root / "receipts" / "gate-bypasses" / "open.json")}
    ]


def test_gate_status_wrapper_builds_real_waiver_summary_when_helper_needs_repo_root(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_real_waiver_summary", WRAPPER_PATH)
    repo_root = tmp_path
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "__init__.py").write_text("", encoding="utf-8")
    (scripts_dir / "controller_automation_toolkit.py").write_text(
        """
def emit_cli_error(exc, *args, **kwargs):
    return None
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (scripts_dir / "gate_bypass_waivers.py").write_text(
        """
from scripts.controller_automation_toolkit import emit_cli_error

def summarize_receipts(*, directory):
    return {
        "totals": {
            "all_receipts": 3,
            "legacy_receipts": 1,
            "compliant_receipts": 2,
            "open_waivers": 1,
            "expired_waivers": 0,
            "invalid_receipts": 0,
        },
        "latest_receipt": {"path": str(directory / "latest.json")},
        "open_waivers": [{"path": str(directory / "open.json")}],
        "expiring_soon": [],
        "warnings": [],
        "release_blockers": [],
        "invalid_receipts": [],
    }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (scripts_dir / "gate_status.py").write_text(
        """
def build_status_payload(*, manifest_path, last_run_path, post_merge_run_path, bypass_dir):
    return {
        "manifest_path": str(manifest_path),
        "enabled_checks": [],
        "last_run": None,
        "post_merge_run": None,
        "latest_bypass": None,
    }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config").mkdir()
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)
    (repo_root / ".local" / "validation-gate").mkdir(parents=True)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["waiver_summary"]["totals"]["all_receipts"] == 3
    assert payload["gate_status"]["waiver_summary"]["open_waivers"] == [
        {"path": str(repo_root / "receipts" / "gate-bypasses" / "open.json")}
    ]


def test_gate_status_wrapper_falls_back_when_waiver_helper_is_missing(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_missing_waiver_helper", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "gate_status.py").write_text(
        """
import gate_bypass_waivers

def build_status_payload(*, manifest_path, last_run_path, post_merge_run_path, bypass_dir):
    return {
        "manifest_path": str(manifest_path),
        "waiver_summary": gate_bypass_waivers.summarize_receipts(directory=bypass_dir),
    }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["waiver_summary"]["totals"] == {
        "all_receipts": 0,
        "legacy_receipts": 0,
        "compliant_receipts": 0,
        "open_waivers": 0,
        "expired_waivers": 0,
        "invalid_receipts": 0,
    }
    assert payload["gate_status"]["waiver_summary"]["release_blockers"] == []


def test_gate_status_wrapper_uses_helper_when_yaml_is_missing(monkeypatch, tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_yaml_fallback", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir()
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)
    (repo_root / ".local" / "validation-gate").mkdir(parents=True)
    helper_path = repo_root / "scripts" / "run_python_with_packages.sh"
    helper_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    helper_path.chmod(0o755)
    (repo_root / "scripts" / "gate_status.py").write_text("raise SystemExit('should not import directly')\n", encoding="utf-8")

    def fake_run(command, *, cwd, text, capture_output, check):
        assert command[0] == str(helper_path)
        assert command[-2:] == ["--format", "json"]
        assert cwd == repo_root
        assert text is True
        assert capture_output is True
        assert check is False
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(
                {
                    "manifest_path": str(repo_root / "config" / "validation-gate.json"),
                    "enabled_checks": [],
                    "waiver_summary": {
                        "totals": {
                            "all_receipts": 1,
                            "legacy_receipts": 0,
                            "compliant_receipts": 1,
                            "open_waivers": 0,
                            "expired_waivers": 0,
                            "invalid_receipts": 0,
                        },
                        "latest_receipt": None,
                        "open_waivers": [],
                        "expiring_soon": [],
                        "warnings": [],
                        "release_blockers": [],
                        "invalid_receipts": [],
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(module, "_yaml_module_available", lambda: False)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["waiver_summary"]["totals"]["all_receipts"] == 1
