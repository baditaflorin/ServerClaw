from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]


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


def write_fake_docker(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import subprocess",
                "import sys",
                "",
                "args = sys.argv[1:]",
                "command = args[args.index('sh') + 2]",
                "raise SystemExit(subprocess.run(['sh', '-c', command]).returncode)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_run_gate_writes_status_file(tmp_path: Path, capsys) -> None:
    run_gate = load_module("run_gate", "scripts/run_gate.py")
    manifest_path = tmp_path / "validation-gate.json"
    manifest_path.write_text(
        json.dumps(
            {
                "alpha": {
                    "description": "first check",
                    "severity": "error",
                    "image": "example/alpha:latest",
                    "command": "printf alpha",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
                "beta": {
                    "description": "second check",
                    "severity": "error",
                    "image": "example/beta:latest",
                    "command": "printf beta",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
            }
        ),
        encoding="utf-8",
    )
    status_path = tmp_path / "last-run.json"
    fake_docker = tmp_path / "fake-docker"
    write_fake_docker(fake_docker)

    exit_code = run_gate.main(
        [
            "--manifest",
            str(manifest_path),
            "--workspace",
            str(tmp_path),
            "--docker-binary",
            str(fake_docker),
            "--status-file",
            str(status_path),
            "--source",
            "test",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "alpha" in captured.out
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["source"] == "test"
    assert payload["session_workspace"]["session_slug"]
    assert payload["session_workspace"]["local_state_root"].endswith(
        f".local/session-workspaces/{payload['session_workspace']['session_slug']}"
    )
    assert [check["id"] for check in payload["checks"]] == ["alpha", "beta"]


def test_log_gate_bypass_writes_receipt(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "receipts"
    completed = subprocess.run(
        [
            "python3",
            str(REPO_ROOT / "scripts" / "log_gate_bypass.py"),
            "--bypass",
            "skip_remote_gate",
            "--reason",
            "test-case",
            "--receipt-dir",
            str(receipt_dir),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    receipt_path = Path(completed.stdout.strip())
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["bypass"] == "skip_remote_gate"
    assert payload["reason"] == "test-case"


def test_gate_status_reports_latest_bypass_and_runs(tmp_path: Path, capsys) -> None:
    gate_status = load_module("gate_status", "scripts/gate_status.py")
    manifest_path = tmp_path / "validation-gate.json"
    manifest_path.write_text(
        json.dumps(
            {
                "ansible-lint": {
                    "description": "lint",
                    "severity": "error",
                    "image": "example",
                    "command": "true",
                    "working_dir": "/workspace",
                    "timeout_seconds": 10,
                }
            }
        ),
        encoding="utf-8",
    )
    last_run = tmp_path / "last-run.json"
    last_run.write_text(
        json.dumps({"status": "passed", "executed_at": "2026-03-23T12:00:00+00:00", "source": "manual"}),
        encoding="utf-8",
    )
    post_merge = tmp_path / "post-merge-last-run.json"
    post_merge.write_text(
        json.dumps({"status": "failed", "executed_at": "2026-03-23T13:00:00+00:00", "source": "windmill"}),
        encoding="utf-8",
    )
    bypass_dir = tmp_path / "gate-bypasses"
    bypass_dir.mkdir()
    (bypass_dir / "20260323T140000Z-main-deadbee-skip.json").write_text(
        json.dumps({"bypass": "skip_remote_gate", "created_at": "2026-03-23T14:00:00+00:00"}),
        encoding="utf-8",
    )

    old_argv = sys.argv[:]
    try:
        sys.argv = [
            "gate_status.py",
            "--manifest",
            str(manifest_path),
            "--last-run",
            str(last_run),
            "--post-merge-run",
            str(post_merge),
            "--bypass-dir",
            str(bypass_dir),
        ]
        exit_code = gate_status.main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Last gate run: passed" in captured.out
    assert "Last post-merge gate run: failed" in captured.out
    assert "Latest bypass receipt:" in captured.out


def test_gate_status_supports_json_output(tmp_path: Path, capsys) -> None:
    gate_status = load_module("gate_status_json", "scripts/gate_status.py")
    manifest_path = tmp_path / "validation-gate.json"
    manifest_path.write_text(
        json.dumps(
            {
                "yaml-lint": {
                    "description": "lint yaml",
                    "severity": "warning",
                }
            }
        ),
        encoding="utf-8",
    )
    old_argv = sys.argv[:]
    try:
        sys.argv = [
            "gate_status.py",
            "--manifest",
            str(manifest_path),
            "--last-run",
            str(tmp_path / "missing-last-run.json"),
            "--post-merge-run",
            str(tmp_path / "missing-post-merge.json"),
            "--bypass-dir",
            str(tmp_path / "missing-bypasses"),
            "--format",
            "json",
        ]
        exit_code = gate_status.main()
    finally:
        sys.argv = old_argv

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["enabled_checks"] == [
        {
            "description": "lint yaml",
            "id": "yaml-lint",
            "severity": "warning",
        }
    ]
    assert payload["last_run"] is None
    assert payload["post_merge_run"] is None
    assert payload["latest_bypass"] is None


def test_gate_status_workflow_catalog_and_windmill_seed_align() -> None:
    catalog = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
    runtime_defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text(
            encoding="utf-8"
        )
    )
    script_paths = {entry["path"] for entry in runtime_defaults["windmill_seed_scripts"]}

    assert "config/windmill/scripts/gate-status.py" in catalog["workflows"]["gate-status"]["implementation_refs"]
    assert "f/lv3/gate-status" in script_paths
