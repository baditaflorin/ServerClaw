from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "gate-status.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def write_gate_status_script(repo_root: Path, body: str) -> None:
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "gate_status.py").write_text(body.strip() + "\n", encoding="utf-8")


def write_script(repo_root: Path, name: str, body: str) -> None:
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / name).write_text(body.strip() + "\n", encoding="utf-8")


def test_gate_status_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_missing", WRAPPER_PATH)
    payload = module.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_gate_status_wrapper_reads_repo_status_payload(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_present", WRAPPER_PATH)
    repo_root = tmp_path
    write_gate_status_script(
        repo_root,
        """
import json
from pathlib import Path

payload = {
    "manifest_path": str((Path.cwd() / "config" / "validation-gate.json")),
    "enabled_checks": [{"id": "agent-standards"}],
    "last_run": {"status": "passed"},
}
print(json.dumps(payload))
""",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["returncode"] == 0
    assert payload["gate_status"]["manifest_path"].endswith("config/validation-gate.json")
    assert payload["gate_status"]["last_run"] == {"status": "passed"}
    assert payload["gate_status"]["enabled_checks"] == [{"id": "agent-standards"}]
    assert payload["command"].endswith("--format json")


def test_gate_status_wrapper_injects_waiver_summary_when_missing(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_waiver_summary", WRAPPER_PATH)
    repo_root = tmp_path
    write_gate_status_script(
        repo_root,
        """
import json

print(json.dumps({"manifest_path": "manifest.json", "enabled_checks": [{"id": "agent-standards"}]}))
""",
    )
    write_script(
        repo_root,
        "gate_bypass_waivers.py",
        """
from pathlib import Path

def summarize_receipts(*, directory: Path):
    return {
        "receipt_dir": str(directory),
        "totals": {"compliant_receipts": 3},
        "release_blockers": [],
    }
""",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["waiver_summary"]["totals"]["compliant_receipts"] == 3
    assert payload["gate_status"]["waiver_summary"]["release_blockers"] == []


def test_gate_status_wrapper_preserves_existing_waiver_summary(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_existing_waiver_summary", WRAPPER_PATH)
    repo_root = tmp_path
    write_gate_status_script(
        repo_root,
        """
import json

print(json.dumps({
    "manifest_path": "manifest.json",
    "enabled_checks": [{"id": "agent-standards"}],
    "waiver_summary": {
        "totals": {"compliant_receipts": 7},
        "release_blockers": [{"reason_code": "existing"}],
    },
}))
""",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["waiver_summary"]["totals"]["compliant_receipts"] == 7
    assert payload["gate_status"]["waiver_summary"]["release_blockers"] == [{"reason_code": "existing"}]


def test_gate_status_wrapper_falls_back_when_waiver_summary_helper_is_missing(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_missing_waiver_summary_helper", WRAPPER_PATH)
    repo_root = tmp_path
    write_gate_status_script(
        repo_root,
        """
import json

print(json.dumps({"manifest_path": "manifest.json", "enabled_checks": [{"id": "agent-standards"}]}))
""",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["waiver_summary"]["totals"]["compliant_receipts"] == 0
    assert payload["gate_status"]["waiver_summary"]["release_blockers"] == []
    assert "summary_error" in payload["gate_status"]["waiver_summary"]


def test_gate_status_wrapper_prefers_helper_runner_when_available(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_helper", WRAPPER_PATH)
    repo_root = tmp_path
    write_gate_status_script(
        repo_root,
        """
raise SystemExit("direct execution should not run when the helper exists")
""",
    )
    helper_path = repo_root / "scripts" / "run_python_with_packages.sh"
    helper_path.write_text(
        """#!/bin/sh
printf '%s\n' '{"manifest_path":"helper-manifest","enabled_checks":[{"id":"schema-validation"}]}'
""",
        encoding="utf-8",
    )
    helper_path.chmod(0o755)

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "ok"
    assert payload["gate_status"]["manifest_path"] == "helper-manifest"
    assert payload["gate_status"]["enabled_checks"] == [{"id": "schema-validation"}]
    assert payload["command"].startswith(str(helper_path))


def test_gate_status_wrapper_reports_non_json_stdout_as_structured_error(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_non_json", WRAPPER_PATH)
    repo_root = tmp_path
    write_gate_status_script(
        repo_root,
        """
print("Validation gate manifest: noisy helper output")
""",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "error"
    assert payload["reason"] == "gate status command returned non-JSON stdout"
    assert payload["returncode"] == 0
    assert "Validation gate manifest" in payload["stdout"]


def test_gate_status_wrapper_reports_empty_stdout_as_structured_error(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_empty", WRAPPER_PATH)
    repo_root = tmp_path
    write_gate_status_script(
        repo_root,
        """
if __name__ == "__main__":
    raise SystemExit(0)
""",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "error"
    assert payload["reason"] == "gate status command returned empty stdout"
    assert payload["returncode"] == 0


def test_gate_status_wrapper_reports_command_failure_as_structured_error(tmp_path: Path) -> None:
    module = load_module("gate_status_windmill_failure", WRAPPER_PATH)
    repo_root = tmp_path
    write_gate_status_script(
        repo_root,
        """
import sys

print("boom", file=sys.stderr)
raise SystemExit(2)
""",
    )

    payload = module.main(repo_path=str(repo_root))

    assert payload["status"] == "error"
    assert payload["reason"] == "gate status command failed"
    assert payload["returncode"] == 2
    assert payload["stderr"] == "boom"
