from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "parallel_check.py"


def load_parallel_check_module():
    spec = importlib.util.spec_from_file_location("parallel_check", MODULE_PATH)
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


def test_load_manifest_and_build_docker_command(tmp_path: Path) -> None:
    parallel_check = load_parallel_check_module()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "lint-yaml": {
                    "image": "registry.lv3.org/check-runner/ansible:2.17.10",
                    "command": "echo ok",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                }
            }
        ),
        encoding="utf-8",
    )

    manifest = parallel_check.load_manifest(manifest_path)
    check = manifest["lint-yaml"]
    command = parallel_check.build_docker_command(check, tmp_path, "docker")

    assert command[:5] == ["docker", "run", "--rm", "--cpus=4", "-v"]
    assert command[-3:] == ["sh", "-c", "echo ok"]


def test_build_docker_command_marks_workspace_as_safe_git_directory(tmp_path: Path) -> None:
    parallel_check = load_parallel_check_module()
    check = parallel_check.CheckDefinition(
        label="schema-validation",
        image="registry.lv3.org/check-runner/python:3.12.10",
        command="python scripts/validate_repository_data_models.py --validate",
        working_dir="/workspace",
        timeout_seconds=30,
    )

    command = parallel_check.build_docker_command(check, tmp_path, "docker")

    assert "GIT_CONFIG_COUNT=1" in command
    assert "GIT_CONFIG_KEY_0=safe.directory" in command
    assert "GIT_CONFIG_VALUE_0=/workspace" in command


def test_build_docker_command_mounts_worktree_git_metadata(tmp_path: Path) -> None:
    parallel_check = load_parallel_check_module()
    repo_root = tmp_path / "repo"
    workspace = repo_root / ".worktrees" / "adr-0083"
    gitdir = repo_root / ".git" / "worktrees" / "adr-0083"
    common_dir = repo_root / ".git"

    workspace.mkdir(parents=True)
    gitdir.mkdir(parents=True)
    common_dir.mkdir(parents=True, exist_ok=True)
    (workspace / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    (gitdir / "commondir").write_text("../..\n", encoding="utf-8")

    check = parallel_check.CheckDefinition(
        label="validate-schemas",
        image="registry.lv3.org/check-runner/python:3.12.10",
        command="python scripts/validate_repository_data_models.py --validate",
        working_dir="/workspace",
        timeout_seconds=30,
    )

    command = parallel_check.build_docker_command(check, workspace, "docker")

    assert f"{workspace.resolve()}:/workspace" in command
    assert f"{gitdir.resolve()}:{gitdir.resolve()}:ro" in command
    assert f"{common_dir.resolve()}:{common_dir.resolve()}:ro" in command


def test_build_docker_command_mounts_declared_caches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parallel_check = load_parallel_check_module()
    collections_dir = tmp_path / "collections-cache"
    packer_dir = tmp_path / "packer-cache"
    policy_dir = tmp_path / "policy-cache"
    trivy_dir = tmp_path / "trivy-cache"
    collections_dir.mkdir()
    packer_dir.mkdir()
    policy_dir.mkdir()
    trivy_dir.mkdir()
    monkeypatch.setenv("LV3_ANSIBLE_COLLECTIONS_DIR", str(collections_dir))
    monkeypatch.setenv("LV3_PACKER_PLUGIN_CACHE_DIR", str(packer_dir))
    monkeypatch.setenv("LV3_POLICY_TOOLCHAIN_ROOT", str(policy_dir))
    monkeypatch.setenv("LV3_TRIVY_CACHE_DIR", str(trivy_dir))

    check = parallel_check.CheckDefinition(
        label="security-scan",
        image="registry.lv3.org/check-runner/security:2026.03.23",
        command="trivy fs .",
        working_dir="/workspace",
        timeout_seconds=30,
        cache_mounts=("ansible_collections", "packer_plugins", "policy_tools", "trivy"),
    )

    command = parallel_check.build_docker_command(check, tmp_path, "docker")

    assert f"{collections_dir.resolve()}:/opt/lv3/ansible-collections" in command
    assert "LV3_ANSIBLE_COLLECTIONS_DIR=/opt/lv3/ansible-collections" in command
    assert f"{packer_dir.resolve()}:/root/.packer.d" in command
    assert "PACKER_CACHE_ROOT=/root/.packer.d" in command
    assert "PACKER_PLUGIN_PATH=/root/.packer.d/plugins" in command
    assert f"{policy_dir.resolve()}:/opt/lv3/policy-toolchain" in command
    assert "LV3_POLICY_TOOLCHAIN_ROOT=/opt/lv3/policy-toolchain" in command
    assert f"{trivy_dir.resolve()}:/var/lib/trivy" in command
    assert "TRIVY_CACHE_DIR=/var/lib/trivy" in command


def test_build_docker_command_forwards_validation_context(tmp_path: Path, monkeypatch) -> None:
    parallel_check = load_parallel_check_module()
    monkeypatch.setenv("LV3_SNAPSHOT_BRANCH", "codex/adr-0264-live-apply")
    monkeypatch.setenv("LV3_VALIDATION_BASE_REF", "origin/main")
    monkeypatch.setenv(
        "LV3_VALIDATION_CHANGED_FILES_JSON",
        '["config/validation-gate.json", "scripts/run_gate.py"]',
    )

    check = parallel_check.CheckDefinition(
        label="workstream-surfaces",
        image="registry.lv3.org/check-runner/python:3.12.10",
        command="./scripts/validate_repo.sh workstream-surfaces",
        working_dir="/workspace",
        timeout_seconds=30,
    )

    command = parallel_check.build_docker_command(check, tmp_path, "docker")

    assert "LV3_SNAPSHOT_BRANCH=codex/adr-0264-live-apply" in command
    assert "LV3_VALIDATION_BASE_REF=origin/main" in command
    assert (
        'LV3_VALIDATION_CHANGED_FILES_JSON=["config/validation-gate.json", "scripts/run_gate.py"]'
        in command
    )


def test_run_checks_returns_non_zero_when_any_check_fails(tmp_path: Path) -> None:
    parallel_check = load_parallel_check_module()
    fake_docker = tmp_path / "fake-docker"
    write_fake_docker(fake_docker)

    checks = [
        parallel_check.CheckDefinition(
            label="ok",
            image="example/ok:latest",
            command="printf ok",
            working_dir="/workspace",
            timeout_seconds=30,
        ),
        parallel_check.CheckDefinition(
            label="fail",
            image="example/fail:latest",
            command="echo broken >&2; exit 1",
            working_dir="/workspace",
            timeout_seconds=30,
        ),
    ]

    results = parallel_check.run_checks(checks, tmp_path, str(fake_docker), jobs=2)

    assert [result.status for result in results] == ["passed", "failed"]
    assert results[1].returncode == 1


def test_execute_check_marks_missing_docker_as_runner_unavailable(tmp_path: Path) -> None:
    parallel_check = load_parallel_check_module()
    check = parallel_check.CheckDefinition(
        label="schema-validation",
        image="example/schema:latest",
        command="true",
        working_dir="/workspace",
        timeout_seconds=30,
    )

    result = parallel_check.execute_check(check, tmp_path, str(tmp_path / "missing-docker"))

    assert result.status == "runner_unavailable"
    assert result.returncode == 127


def test_main_supports_all_checks(tmp_path: Path, capsys) -> None:
    parallel_check = load_parallel_check_module()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "first": {
                    "image": "example/first:latest",
                    "command": "printf first",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
                "second": {
                    "image": "example/second:latest",
                    "command": "printf second",
                    "working_dir": "/workspace",
                    "timeout_seconds": 30,
                },
            }
        ),
        encoding="utf-8",
    )
    fake_docker = tmp_path / "fake-docker"
    write_fake_docker(fake_docker)

    exit_code = parallel_check.main(
        [
            "--all",
            "--manifest",
            str(manifest_path),
            "--workspace",
            str(tmp_path),
            "--docker-binary",
            str(fake_docker),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "CHECK" in captured.out
    assert "first" in captured.out
    assert "second" in captured.out
