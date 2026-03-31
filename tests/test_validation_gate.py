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
                "import json",
                "import subprocess",
                "import sys",
                "",
                "args = sys.argv[1:]",
                "if args == ['--version']:",
                "    print('Docker version 26.1.0, build fake')",
                "    raise SystemExit(0)",
                "if args[:2] == ['info', '--format']:",
                "    print('26.1.0')",
                "    raise SystemExit(0)",
                "command = args[args.index('sh') + 2]",
                "raise SystemExit(subprocess.run(['sh', '-c', command]).returncode)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_runner_contracts(
    path: Path,
    *,
    lane_ids: list[str],
    runner_id: str = "test-runner",
    supported_lane_ids: list[str] | None = None,
) -> None:
    supported_lanes = supported_lane_ids or lane_ids
    path.write_text(
        json.dumps(
            {
                "$schema": "docs/schema/validation-runner-contracts.schema.json",
                "schema_version": "1.0.0",
                "lanes": {
                    lane_id: {
                        "description": f"{lane_id} lane",
                        "requires_container_runtime": True,
                        "required_tools": ["docker", "python3", "tar"],
                        "allowed_network_reachability_classes": ["controller_local"],
                        "allowed_cpu_architectures": ["arm64", "x86_64"],
                        "require_scratch_cleanup_guarantee": True,
                    }
                    for lane_id in lane_ids
                },
                "runners": {
                    runner_id: {
                        "description": "test runner",
                        "execution_surface": "controller_local",
                        "cpu_architectures": ["arm64", "x86_64"],
                        "emulation_support": [],
                        "container_runtime": {"engine": "docker", "supported": True},
                        "required_tools": ["docker", "python3", "tar"],
                        "network_reachability_class": "controller_local",
                        "scratch_cleanup_guarantee": "temp workspace",
                        "supported_validation_lanes": supported_lanes,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


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
    runner_contracts = tmp_path / "validation-runner-contracts.json"
    write_fake_docker(fake_docker)
    write_runner_contracts(runner_contracts, lane_ids=["alpha", "beta"])

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
            "--runner-id",
            "test-runner",
            "--runner-contracts",
            str(runner_contracts),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "alpha" in captured.out
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["source"] == "test"
    assert payload["runner"]["id"] == "test-runner"
    assert payload["session_workspace"]["session_slug"]
    assert payload["session_workspace"]["local_state_root"].endswith(
        f".local/session-workspaces/{payload['session_workspace']['session_slug']}"
    )
    assert [check["id"] for check in payload["checks"]] == ["alpha", "beta"]


def test_run_gate_auto_selects_docs_lane_checks(tmp_path: Path) -> None:
    run_gate = load_module("run_gate_docs_lane", "scripts/run_gate.py")
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "docs" / "adr").mkdir(parents=True)
    manifest_path = repo_root / "config" / "validation-gate.json"
    manifest_path.write_text(
        json.dumps(
            {
                "workstream-surfaces": {
                    "description": "ownership",
                    "severity": "error",
                    "image": "example/python:latest",
                    "command": "printf workstream",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
                "agent-standards": {
                    "description": "agent standards",
                    "severity": "error",
                    "image": "example/python:latest",
                    "command": "printf standards",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
                "documentation-index": {
                    "description": "documentation index",
                    "severity": "error",
                    "image": "example/python:latest",
                    "command": "printf docs-index",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
                "security-scan": {
                    "description": "security",
                    "severity": "error",
                    "image": "example/security:latest",
                    "command": "printf security",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
            }
        ),
        encoding="utf-8",
    )
    lane_catalog_path = repo_root / "config" / "validation-lanes.yaml"
    lane_catalog_path.write_text(
        "\n".join(
            [
                "schema_version: 1.0.0",
                "primary_branch: main",
                "unknown_surface_policy: all_lanes",
                "fast_global_checks:",
                "  - workstream-surfaces",
                "  - agent-standards",
                "lanes:",
                "  documentation-and-adr:",
                "    title: Documentation",
                "    description: Doc lane",
                "    checks:",
                "      - documentation-index",
                "  remote-builder:",
                "    title: Remote builder",
                "    description: Builder lane",
                "    checks:",
                "      - security-scan",
                "surface_classes:",
                "  - surface_id: docs",
                "    title: Docs",
                "    paths:",
                "      - docs/adr/*.md",
                "    required_lanes:",
                "      - documentation-and-adr",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    doc_path = repo_root / "docs" / "adr" / "0264-test.md"
    doc_path.write_text("# ADR test\n", encoding="utf-8")
    status_path = repo_root / ".local" / "validation-gate" / "last-run.json"
    fake_docker = tmp_path / "fake-docker"
    runner_contracts = tmp_path / "validation-runner-contracts.json"
    write_fake_docker(fake_docker)
    write_runner_contracts(
        runner_contracts,
        lane_ids=[
            "workstream-surfaces",
            "agent-standards",
            "documentation-index",
            "security-scan",
        ],
    )

    subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo_root), "config", "user.email", "codex@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "config", "user.name", "Codex"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m", "initial"], check=True, capture_output=True, text=True)
    base_branch = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(repo_root), "checkout", "-b", "codex/docs-change"], check=True, capture_output=True, text=True)
    doc_path.write_text("# ADR test\n\nUpdated.\n", encoding="utf-8")

    exit_code = run_gate.main(
        [
            "--manifest",
            str(manifest_path),
            "--workspace",
            str(repo_root),
            "--lane-catalog",
            str(lane_catalog_path),
            "--docker-binary",
            str(fake_docker),
            "--status-file",
            str(status_path),
            "--base-ref",
            base_branch,
            "--runner-id",
            "test-runner",
            "--runner-contracts",
            str(runner_contracts),
        ]
    )

    assert exit_code == 0
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["requested_checks"] == ["workstream-surfaces", "agent-standards", "documentation-index"]
    assert payload["lane_selection"]["selected_lanes"] == ["documentation-and-adr"]
    assert payload["lane_selection"]["unknown_files"] == []
    assert payload["lane_results"][0]["green_path_summary"] == (
        "Documentation passed for 1 changed file(s) via documentation-index."
    )
    assert payload["runner"]["id"] == "test-runner"


def test_run_gate_reports_runner_unavailable_without_crashing(tmp_path: Path, capsys) -> None:
    run_gate = load_module("run_gate_runner_unavailable", "scripts/run_gate.py")
    manifest_path = tmp_path / "validation-gate.json"
    manifest_path.write_text(
        json.dumps(
            {
                "alpha": {
                    "description": "alpha check",
                    "severity": "error",
                    "image": "example/alpha:latest",
                    "command": "printf alpha",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
                "beta": {
                    "description": "beta check",
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
    runner_contracts = tmp_path / "validation-runner-contracts.json"
    write_fake_docker(fake_docker)
    write_runner_contracts(
        runner_contracts,
        lane_ids=["alpha", "beta"],
        supported_lane_ids=["beta"],
    )

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
            "--runner-id",
            "test-runner",
            "--runner-contracts",
            str(runner_contracts),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "alpha" in captured.out
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert [check["id"] for check in payload["checks"]] == ["alpha", "beta"]
    assert payload["checks"][0]["status"] == "runner_unavailable"
    assert payload["checks"][1]["status"] == "passed"


def test_log_gate_bypass_writes_receipt(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "receipts"
    completed = subprocess.run(
        [
            "python3",
            str(REPO_ROOT / "scripts" / "log_gate_bypass.py"),
            "--bypass",
            "skip_remote_gate",
            "--reason-code",
            "build_server_unreachable",
            "--detail",
            "test-case",
            "--impacted-lane",
            "remote-pre-push-gate",
            "--substitute-evidence",
            "./scripts/validate_repo.sh agent-standards",
            "--remediation-ref",
            "ws-0267-live-apply",
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
    assert payload["waiver"]["reason_code"] == "build_server_unreachable"
    assert payload["waiver"]["detail"] == "test-case"
    assert payload["waiver"]["remediation_ref"] == "ws-0267-live-apply"
    assert payload["waiver"]["substitute_evidence"] == ["./scripts/validate_repo.sh agent-standards"]


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
    assert "Waiver summary:" in captured.out


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
    assert payload["waiver_summary"]["totals"]["all_receipts"] == 0
    assert payload["waiver_summary"]["release_blockers"] == []


def test_gate_status_resolves_default_paths_from_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "config").mkdir(parents=True)
    (repo_root / ".local" / "validation-gate").mkdir(parents=True)
    (repo_root / "receipts" / "gate-bypasses").mkdir(parents=True)

    for relative_path in (
        "scripts/__init__.py",
        "scripts/gate_bypass_waivers.py",
        "scripts/gate_status.py",
        "scripts/validation_lanes.py",
        "config/gate-bypass-waiver-catalog.json",
        "config/validation-gate.json",
        "config/validation-lanes.yaml",
    ):
        destination = repo_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / relative_path).read_text(encoding="utf-8"), encoding="utf-8")

    (repo_root / "scripts" / "controller_automation_toolkit.py").write_text(
        "def emit_cli_error(*args, **kwargs):\n    return None\n",
        encoding="utf-8",
    )

    (repo_root / ".local" / "validation-gate" / "post-merge-last-run.json").write_text(
        json.dumps({"status": "passed", "executed_at": "2026-03-29T16:39:41+00:00", "source": "windmill"}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "gate_status.py"), "--format", "json"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["manifest_path"] == str(repo_root / "config" / "validation-gate.json")
    assert payload["lane_catalog_path"] == str(repo_root / "config" / "validation-lanes.yaml")
    assert len(payload["enabled_checks"]) >= 1
    assert payload["post_merge_run"] == {
        "status": "passed",
        "executed_at": "2026-03-29T16:39:41+00:00",
        "source": "windmill",
    }


def test_gate_status_workflow_catalog_and_windmill_seed_align() -> None:
    catalog = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
    runtime_defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text(
            encoding="utf-8"
        )
    )
    script_paths = {entry["path"] for entry in runtime_defaults["windmill_seed_scripts"]}

    assert "config/windmill/scripts/gate-status.py" in catalog["workflows"]["gate-status"]["implementation_refs"]
    assert "config/windmill/scripts/stage-smoke-suites.py" in catalog["workflows"]["stage-smoke-suites"]["implementation_refs"]
    assert "f/lv3/gate-status" in script_paths
    assert "f/lv3/stage-smoke-suites" in script_paths


def test_gate_status_reexecs_via_python_package_runner_when_yaml_is_missing() -> None:
    script = (REPO_ROOT / "scripts" / "gate_status.py").read_text(encoding="utf-8")

    assert "LV3_GATE_STATUS_PYYAML_BOOTSTRAPPED" in script
    assert "run_python_with_packages.sh" in script


def test_run_gate_reexecs_via_python_package_runner_when_yaml_is_missing() -> None:
    script = (REPO_ROOT / "scripts" / "run_gate.py").read_text(encoding="utf-8")

    assert "LV3_RUN_GATE_PYYAML_BOOTSTRAPPED" in script
    assert "run_python_with_packages.sh" in script
