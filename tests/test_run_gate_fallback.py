from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_gate_fallback_reruns_only_remote_failures_and_merges_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module("run_gate_fallback_merge", "scripts/run_gate_fallback.py")
    status_path = tmp_path / "last-run.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "failed",
                "source": "build-server",
                "requested_checks": [
                    "policy-validation",
                    "packer-validate",
                    "tofu-validate",
                ],
                "checks": [
                    {"id": "policy-validation", "status": "passed", "returncode": 0},
                    {"id": "packer-validate", "status": "runner_unavailable", "returncode": 69},
                    {"id": "tofu-validate", "status": "runner_unavailable", "returncode": 69},
                ],
                "lane_results": [
                    {
                        "lane_id": "remote-builder",
                        "title": "Remote Builder",
                        "status": "failed",
                        "selected": True,
                        "selected_checks": ["packer-validate", "tofu-validate"],
                        "matched_files": ["config/build-server.json"],
                    }
                ],
                "fast_global_results": [
                    {
                        "id": "policy-validation",
                        "description": "policy",
                        "severity": "error",
                        "status": "passed",
                        "returncode": 0,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    captured_command: list[str] = []

    def fake_run(command, cwd, text, capture_output, check):
        nonlocal captured_command
        captured_command = command
        temp_status_path = Path(command[command.index("--status-file") + 1])
        temp_status_path.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "source": "local-fallback",
                    "workspace": str(cwd),
                    "session_workspace": {"session_id": "local"},
                    "manifest": str(Path(cwd) / "config" / "validation-gate.json"),
                    "executed_at": "2026-03-31T16:00:00+00:00",
                    "runner": {"id": "controller-local-validation"},
                    "checks": [
                        {"id": "packer-validate", "status": "passed", "returncode": 0},
                        {"id": "tofu-validate", "status": "passed", "returncode": 0},
                    ],
                    "requested_checks": ["packer-validate", "tofu-validate"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="partial-ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main(
        [
            "--workspace",
            str(tmp_path),
            "--status-file",
            str(status_path),
            "--source",
            "local-fallback",
            "schema-validation",
        ]
    )

    assert rc == 0
    assert captured_command[-2:] == ["packer-validate", "tofu-validate"]
    merged = json.loads(status_path.read_text(encoding="utf-8"))
    assert merged["status"] == "passed"
    assert merged["requested_checks"] == [
        "policy-validation",
        "packer-validate",
        "tofu-validate",
    ]
    assert [check["id"] for check in merged["checks"]] == [
        "policy-validation",
        "packer-validate",
        "tofu-validate",
    ]
    assert all(check["status"] == "passed" for check in merged["checks"])
    assert merged["lane_results"][0]["status"] == "passed"


def test_run_gate_fallback_ignores_stale_local_status_and_runs_requested_checks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module("run_gate_fallback_stale", "scripts/run_gate_fallback.py")
    status_path = tmp_path / "last-run.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "failed",
                "source": "local-fallback",
                "checks": [{"id": "artifact-secret-scan", "status": "timed_out", "returncode": 124}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    captured_command: list[str] = []

    def fake_run(command, cwd, text, capture_output, check):
        nonlocal captured_command
        captured_command = command
        temp_status_path = Path(command[command.index("--status-file") + 1])
        temp_status_path.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "source": "local-fallback",
                    "workspace": str(cwd),
                    "session_workspace": {"session_id": "local"},
                    "manifest": str(Path(cwd) / "config" / "validation-gate.json"),
                    "executed_at": "2026-03-31T16:01:00+00:00",
                    "runner": {"id": "controller-local-validation"},
                    "checks": [
                        {"id": "schema-validation", "status": "passed", "returncode": 0},
                        {"id": "policy-validation", "status": "passed", "returncode": 0},
                    ],
                    "requested_checks": ["schema-validation", "policy-validation"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main(
        [
            "--workspace",
            str(tmp_path),
            "--status-file",
            str(status_path),
            "--source",
            "local-fallback",
            "schema-validation",
            "policy-validation",
        ]
    )

    assert rc == 0
    assert captured_command[-2:] == ["schema-validation", "policy-validation"]


def test_run_gate_fallback_treats_empty_status_payload_as_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_module("run_gate_fallback_empty_status", "scripts/run_gate_fallback.py")
    status_path = tmp_path / "last-run.json"
    status_path.write_text("", encoding="utf-8")
    captured_command: list[str] = []

    def fake_run(command, cwd, text, capture_output, check):
        nonlocal captured_command
        captured_command = command
        temp_status_path = Path(command[command.index("--status-file") + 1])
        temp_status_path.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "source": "local-fallback",
                    "workspace": str(cwd),
                    "session_workspace": {"session_id": "local"},
                    "manifest": str(Path(cwd) / "config" / "validation-gate.json"),
                    "executed_at": "2026-04-01T10:00:00+00:00",
                    "runner": {"id": "controller-local-validation"},
                    "checks": [
                        {"id": "schema-validation", "status": "passed", "returncode": 0},
                    ],
                    "requested_checks": ["schema-validation"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    rc = module.main(
        [
            "--workspace",
            str(tmp_path),
            "--status-file",
            str(status_path),
            "--source",
            "local-fallback",
            "schema-validation",
        ]
    )

    assert rc == 0
    assert captured_command[-1] == "schema-validation"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["requested_checks"] == ["schema-validation"]
