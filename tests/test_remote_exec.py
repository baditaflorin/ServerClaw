from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "remote_exec.sh"


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


def make_fake_ssh(path: Path) -> None:
    write_executable(
        path,
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${REMOTE_EXEC_SSH_LOG:?}"
if [[ "${REMOTE_EXEC_SSH_FAIL:-0}" == "1" ]]; then
  exit 255
fi
if [[ "$*" == *"docker run"* ]]; then
  printf 'remote-docker-ok\n'
fi
if [[ "$*" == *"build-server-ok"* ]]; then
  printf 'build-server-ok\n'
fi
if [[ "$*" == *" && pwd"* ]]; then
  printf '%s\n' "${REMOTE_EXEC_WORKSPACE_ROOT:?}"
fi
if [[ "$*" == *".local/validation-gate/last-run.json"* ]]; then
  printf '%s' "${REMOTE_EXEC_STATUS_PAYLOAD:-}"
fi
""",
    )


def make_fake_rsync(path: Path) -> None:
    write_executable(
        path,
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${REMOTE_EXEC_RSYNC_LOG:?}"
""",
    )


def build_config(
    path: Path,
    *,
    workspace_root: str,
    local_command: str,
    builtin: str | None = None,
    ssh_options: list[str] | None = None,
) -> None:
    payload = {
        "host": "build-lv3",
        "ssh_key": "~/.ssh/id_ed25519",
        "ssh_options": ssh_options or [],
        "workspace_root": workspace_root,
        "default_timeout_seconds": 120,
        "docker_socket": "unix:///var/run/docker.sock",
        "pip_cache_volume": "pip-cache",
        "packer_plugin_cache": "/opt/builds/.packer.d",
        "ansible_collection_cache": "/opt/builds/.ansible/collections",
        "ansible_requirements_sha_file": "/opt/builds/.ansible/requirements.sha",
        "apt_proxy_url": "http://10.10.10.30:3142",
        "registry_base": "registry.lv3.org",
        "commands": {
            "remote-lint": {
                "runner_label": "lint-ansible",
                "command": "printf remote-lint",
                "local_fallback_command": local_command,
            },
            "remote-validate": {
                "runner_label": "validate-schemas",
                "command": "printf remote-validate",
                "local_fallback_command": local_command,
            },
            "pre-push-gate": {
                "skip_docker": True,
                "command": "printf remote-pre-push",
                "local_fallback_command": local_command,
            },
            "remote-packer-validate": {
                "runner_label": "packer-validate",
                "command": "printf remote-packer-validate",
                "local_fallback_command": local_command,
            },
            "check-build-server": {
                "builtin": builtin or "check-build-server",
            },
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def build_manifest(path: Path) -> None:
    payload = {
        "lint-ansible": {
            "image": "registry.lv3.org/check-runner/ansible:0.1.0",
            "command": ["./scripts/validate_repo.sh", "yaml", "ansible-lint"],
            "working_dir": "/workspace",
            "timeout_seconds": 180,
            "cache_mounts": ["ansible_collections"],
        },
        "validate-schemas": {
            "image": "registry.lv3.org/check-runner/python:0.1.0",
            "command": "python scripts/validate_repository_data_models.py --validate",
            "working_dir": "/workspace",
            "timeout_seconds": 180,
            "cache_mounts": ["pip"],
        },
        "packer-validate": {
            "image": "registry.lv3.org/check-runner/infra:0.1.0",
            "command": "packer validate packer",
            "working_dir": "/workspace",
            "timeout_seconds": 180,
            "cache_mounts": ["packer_plugins"],
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def run_remote_exec(
    tmp_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    ssh_log = tmp_path / "ssh.log"
    rsync_log = tmp_path / "rsync.log"
    marker = tmp_path / "marker.txt"
    config_path = tmp_path / "build-server.json"
    manifest_path = tmp_path / "check-runner-manifest.json"
    exclude_path = tmp_path / "exclude.txt"
    fake_ssh = tmp_path / "ssh"
    fake_rsync = tmp_path / "rsync"

    build_config(
        config_path,
        workspace_root="/opt/builds/proxmox_florin_server",
        local_command="printf local-fallback > \"$REMOTE_EXEC_MARKER\"",
    )
    build_manifest(manifest_path)
    exclude_path.write_text(".local/\n")
    make_fake_ssh(fake_ssh)
    make_fake_rsync(fake_rsync)

    env = os.environ.copy()
    env.update(
        {
            "REMOTE_EXEC_CONFIG": str(config_path),
            "REMOTE_EXEC_RUNNER_MANIFEST": str(manifest_path),
            "REMOTE_EXEC_EXCLUDE_FILE": str(exclude_path),
            "REMOTE_EXEC_SSH_BIN": str(fake_ssh),
            "REMOTE_EXEC_RSYNC_BIN": str(fake_rsync),
            "REMOTE_EXEC_SSH_LOG": str(ssh_log),
            "REMOTE_EXEC_RSYNC_LOG": str(rsync_log),
            "REMOTE_EXEC_WORKSPACE_ROOT": "/opt/builds/proxmox_florin_server",
            "REMOTE_EXEC_MARKER": str(marker),
            "REMOTE_EXEC_STATUS_PAYLOAD": '{"status":"passed","source":"build-server"}\n',
        }
    )
    if extra_env:
        env.update(extra_env)

    completed = subprocess.run(
        [str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    completed.ssh_log = ssh_log  # type: ignore[attr-defined]
    completed.rsync_log = rsync_log  # type: ignore[attr-defined]
    completed.marker = marker  # type: ignore[attr-defined]
    return completed


def test_remote_exec_uses_docker_runner_metadata(tmp_path: Path) -> None:
    completed = run_remote_exec(tmp_path, "remote-lint", extra_env={"REMOTE_EXEC_VERBOSE": "1"})

    assert completed.returncode == 0, completed.stderr
    assert "Remote docker command:" in completed.stderr
    assert "registry.lv3.org/check-runner/ansible:0.1.0" in completed.stderr
    assert "/opt/builds/.ansible/collections:/opt/builds/.ansible/collections" in completed.stderr
    assert "LV3_ANSIBLE_COLLECTIONS_SHA_FILE=/opt/builds/.ansible/requirements.sha" in completed.stderr
    assert "docker run" in completed.ssh_log.read_text()  # type: ignore[attr-defined]
    assert "--checksum" in completed.rsync_log.read_text()  # type: ignore[attr-defined]


def test_remote_exec_falls_back_locally_when_requested(tmp_path: Path) -> None:
    completed = run_remote_exec(
        tmp_path,
        "remote-lint",
        "--local-fallback",
        extra_env={"REMOTE_EXEC_SSH_FAIL": "1"},
    )

    assert completed.returncode == 0
    assert "running local fallback" in completed.stderr
    assert completed.marker.read_text() == "local-fallback"  # type: ignore[attr-defined]


def test_check_build_server_uses_rsync_dry_run(tmp_path: Path) -> None:
    completed = run_remote_exec(tmp_path, "check-build-server")

    assert completed.returncode == 0, completed.stderr
    rsync_log = completed.rsync_log.read_text()  # type: ignore[attr-defined]
    assert "--dry-run" in rsync_log
    assert "--verbose" in rsync_log
    assert "build-server-ok" in completed.stdout


def test_remote_exec_applies_configured_ssh_options(tmp_path: Path) -> None:
    ssh_log = tmp_path / "ssh.log"
    rsync_log = tmp_path / "rsync.log"
    config_path = tmp_path / "build-server.json"
    manifest_path = tmp_path / "check-runner-manifest.json"
    exclude_path = tmp_path / "exclude.txt"
    fake_ssh = tmp_path / "ssh"
    fake_rsync = tmp_path / "rsync"

    build_config(
        config_path,
        workspace_root="/opt/builds/proxmox_florin_server",
        local_command="printf local-fallback > \"$REMOTE_EXEC_MARKER\"",
        ssh_options=["-o", "ProxyCommand=ssh jump.example -W %h:%p"],
    )
    build_manifest(manifest_path)
    exclude_path.write_text(".local/\n")
    make_fake_ssh(fake_ssh)
    make_fake_rsync(fake_rsync)

    env = os.environ.copy()
    env.update(
        {
            "REMOTE_EXEC_CONFIG": str(config_path),
            "REMOTE_EXEC_RUNNER_MANIFEST": str(manifest_path),
            "REMOTE_EXEC_EXCLUDE_FILE": str(exclude_path),
            "REMOTE_EXEC_SSH_BIN": str(fake_ssh),
            "REMOTE_EXEC_RSYNC_BIN": str(fake_rsync),
            "REMOTE_EXEC_SSH_LOG": str(ssh_log),
            "REMOTE_EXEC_RSYNC_LOG": str(rsync_log),
            "REMOTE_EXEC_WORKSPACE_ROOT": "/opt/builds/proxmox_florin_server",
            "REMOTE_EXEC_MARKER": str(tmp_path / "marker.txt"),
        }
    )

    completed = subprocess.run(
        [str(SCRIPT_PATH), "check-build-server"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "ProxyCommand=ssh jump.example -W %h:%p" in ssh_log.read_text()


def test_remote_exec_mounts_pip_cache_for_python_runners(tmp_path: Path) -> None:
    completed = run_remote_exec(tmp_path, "remote-validate", extra_env={"REMOTE_EXEC_VERBOSE": "1"})

    assert completed.returncode == 0, completed.stderr
    assert "pip-cache:/root/.cache/pip" in completed.stderr
    assert "PIP_CACHE_DIR=/root/.cache/pip" in completed.stderr


def test_remote_exec_mounts_packer_cache_for_infra_runners(tmp_path: Path) -> None:
    completed = run_remote_exec(tmp_path, "remote-packer-validate", extra_env={"REMOTE_EXEC_VERBOSE": "1"})

    assert completed.returncode == 0, completed.stderr
    assert "/opt/builds/.packer.d:/root/.packer.d" in completed.stderr


def test_remote_exec_syncs_remote_gate_status_back_to_local_checkout(tmp_path: Path) -> None:
    status_path = REPO_ROOT / ".local" / "validation-gate" / "last-run.json"
    status_path.unlink(missing_ok=True)

    completed = run_remote_exec(tmp_path, "pre-push-gate")

    assert completed.returncode == 0, completed.stderr
    assert status_path.exists()
    assert '"status":"passed"' in status_path.read_text()
