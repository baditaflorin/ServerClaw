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
                "raise SystemExit(subprocess.run(['sh', '-lc', command]).returncode)",
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
    assert command[-3:] == ["sh", "-lc", "echo ok"]


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
