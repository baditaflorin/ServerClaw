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
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--manifest", required=True)
parser.add_argument("--last-run", required=True)
parser.add_argument("--post-merge-run", required=True)
parser.add_argument("--bypass-dir", required=True)
parser.add_argument("--format", required=True)
args = parser.parse_args()
print(json.dumps({
    "manifest_path": args.manifest,
    "enabled_checks": [{"id": "agent-standards"}],
    "last_run": {"status": "passed"},
    "post_merge_run": None,
    "latest_bypass": None,
    "bypass_dir": args.bypass_dir,
}))
""".strip()
        + "\n",
        encoding="utf-8",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["manifest_path"].endswith("config/validation-gate.json")
    assert payload["gate_status"]["last_run"] == {"status": "passed"}


def test_gate_status_wrapper_reports_subprocess_failure(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_failure", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "gate_status.py").write_text(
        """
import sys

sys.stderr.write("boom\\n")
raise SystemExit(7)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "error"
    assert payload["returncode"] == 7
    assert payload["stderr"] == "boom"


def test_decode_gate_status_payload_requires_json_object() -> None:
    module = load_module("gate_status_windmill_decode", WRAPPER_PATH)
    assert module.decode_gate_status_payload(json.dumps({"status": "ok"})) == {"status": "ok"}

    try:
        module.decode_gate_status_payload('["not-an-object"]')
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("expected decode_gate_status_payload to reject non-object payloads")


def test_gate_status_command_uses_expected_cli_contract(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_command", WRAPPER_PATH)
    command = module.gate_status_command(tmp_path)
    assert command == [
        "python3",
        str(tmp_path / "scripts" / "gate_status.py"),
        "--manifest",
        str(tmp_path / "config" / "validation-gate.json"),
        "--last-run",
        str(tmp_path / ".local" / "validation-gate" / "last-run.json"),
        "--post-merge-run",
        str(tmp_path / ".local" / "validation-gate" / "post-merge-last-run.json"),
        "--bypass-dir",
        str(tmp_path / "receipts" / "gate-bypasses"),
        "--format",
        "json",
    ]
