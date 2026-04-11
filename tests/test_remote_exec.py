from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "remote_exec.sh"
SESSION_ID = "test-session"
REMOTE_WORKSPACE_ROOT = f"/opt/builds/proxmox_florin_server/.lv3-session-workspaces/{SESSION_ID}/repo"


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(0o755)


def make_fake_ssh(path: Path) -> None:
    write_executable(
        path,
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${REMOTE_EXEC_SSH_LOG:?}"
stdin_payload="$(cat || true)"
if [[ -n "$stdin_payload" ]]; then
  printf 'STDIN<<EOF\n%s\nEOF\n' "$stdin_payload" >> "${REMOTE_EXEC_SSH_LOG:?}"
fi
if [[ "${REMOTE_EXEC_SSH_FAIL:-0}" == "1" ]]; then
  exit 255
fi
if [[ "${REMOTE_EXEC_REMOTE_FAIL:-0}" == "1" && "$*" != *" true" && "$*" != *"bash -s"* && "$*" != *"mkdir -p"* && "$*" != *"tar -xzf"* && "$*" != *"test -f"* && "$*" != *".local/validation-gate/last-run.json"* && "$*" != *".local/validation-gate/remote-validate-last-run.json"* ]]; then
  exit 1
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
if [[ "$*" == *".local/validation-gate/remote-validate-last-run.json"* ]]; then
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
if [[ "${REMOTE_EXEC_RSYNC_FAIL:-0}" == "1" ]]; then
  exit 23
fi
""",
    )


def make_fake_tailscale(path: Path, *, status_output: str) -> None:
    write_executable(
        path,
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "${{1:-}}" == "status" ]]; then
  cat <<'EOF'
{status_output}
EOF
  exit 0
fi
exit 1
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
                "runner_id": "build-server-validation",
                "local_fallback_runner_id": "controller-local-validation",
                "runner_label": "lint-ansible",
                "validation_lanes": ["yaml-lint", "ansible-lint"],
                "command": "printf remote-lint",
                "local_fallback_command": local_command,
            },
            "remote-validate": {
                "runner_id": "build-server-validation",
                "local_fallback_runner_id": "controller-local-validation",
                "runner_label": "validate-schemas",
                "status_file": ".local/validation-gate/remote-validate-last-run.json",
                "validation_lanes": [
                    "ansible-syntax",
                    "schema-validation",
                    "policy-validation",
                    "alert-rule-validation",
                    "type-check",
                    "dependency-graph",
                ],
                "command": "printf remote-validate",
                "local_fallback_command": local_command,
            },
            "pre-push-gate": {
                "runner_id": "build-server-validation",
                "local_fallback_runner_id": "controller-local-validation",
                "skip_docker": True,
                "status_file": ".local/validation-gate/last-run.json",
                "validation_lanes": "all-validation-gate-checks",
                "command": "printf remote-pre-push",
                "local_fallback_command": local_command,
            },
            "remote-packer-validate": {
                "runner_id": "build-server-validation",
                "local_fallback_runner_id": "controller-local-validation",
                "runner_label": "packer-validate",
                "validation_lanes": ["packer-validate"],
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


def seed_snapshot_env(tmp_path: Path) -> dict[str, str]:
    snapshot_archive = tmp_path / "repository-snapshot-test.tar.gz"
    snapshot_archive.write_bytes(b"snapshot")
    return {
        "LV3_SNAPSHOT_ID": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "LV3_SNAPSHOT_ARCHIVE": str(snapshot_archive),
        "LV3_SNAPSHOT_GENERATED_AT": "2026-04-04T14:30:00+00:00",
        "LV3_SNAPSHOT_SOURCE_COMMIT": "aa86822664ed78182744f322430410c6a1c3e8f0",
        "LV3_SNAPSHOT_BRANCH": "codex/ws-0333-private-overlay",
        "LV3_SNAPSHOT_FILE_COUNT": "1",
    }


def run_remote_exec(
    tmp_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
    ssh_options: list[str] | None = None,
    local_command: str = 'printf local-fallback > "$REMOTE_EXEC_MARKER"',
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
        local_command=local_command,
        ssh_options=ssh_options,
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
            "REMOTE_EXEC_WORKSPACE_ROOT": REMOTE_WORKSPACE_ROOT,
            "REMOTE_EXEC_MARKER": str(marker),
            "REMOTE_EXEC_STATUS_PAYLOAD": '{"status":"passed","source":"build-server"}\n',
            "LV3_SESSION_ID": SESSION_ID,
        }
    )
    env.update(seed_snapshot_env(tmp_path))
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


def extract_run_workspace_root(text: str) -> str:
    match = re.search(
        r"(/opt/builds/proxmox_florin_server/\.lv3-session-workspaces/test-session/repo/\.lv3-runs/[^ ]+/repo)", text
    )
    assert match is not None, text
    return match.group(1)


def test_remote_exec_uses_docker_runner_metadata(tmp_path: Path) -> None:
    completed = run_remote_exec(tmp_path, "remote-lint", extra_env={"REMOTE_EXEC_VERBOSE": "1"})

    assert completed.returncode == 0, completed.stderr
    run_workspace_root = extract_run_workspace_root(completed.stderr)
    assert "Remote docker command:" in completed.stderr
    assert "registry.lv3.org/check-runner/ansible:0.1.0" in completed.stderr
    assert "/opt/builds/.ansible/collections:/opt/builds/.ansible/collections" in completed.stderr
    assert "LV3_ANSIBLE_COLLECTIONS_SHA_FILE=/opt/builds/.ansible/requirements.sha" in completed.stderr
    assert f"{run_workspace_root}:/workspace" in completed.stderr
    assert "GIT_CONFIG_KEY_0=safe.directory" in completed.stderr
    assert "GIT_CONFIG_VALUE_0=/workspace" in completed.stderr
    ssh_log = completed.ssh_log.read_text()  # type: ignore[attr-defined]
    assert "bash -lc" in ssh_log
    assert "check-runner/ansible:0.1.0" in ssh_log
    assert "docker run" in ssh_log
    rsync_log = completed.rsync_log.read_text()  # type: ignore[attr-defined]
    assert "--checksum" in rsync_log
    assert "repository-snapshot-" in rsync_log
    assert ".lv3-snapshots" in rsync_log


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


def test_remote_exec_falls_back_locally_when_sync_fails(tmp_path: Path) -> None:
    completed = run_remote_exec(
        tmp_path,
        "remote-lint",
        "--local-fallback",
        extra_env={"REMOTE_EXEC_RSYNC_FAIL": "1"},
    )

    assert completed.returncode == 0
    assert "snapshot upload failed" in completed.stderr
    assert completed.marker.read_text() == "local-fallback"  # type: ignore[attr-defined]


def test_remote_exec_exports_validate_python_bin_for_local_fallback(tmp_path: Path) -> None:
    completed = run_remote_exec(
        tmp_path,
        "remote-lint",
        "--local-fallback",
        extra_env={"REMOTE_EXEC_SSH_FAIL": "1"},
        local_command='printf %s "${LV3_VALIDATE_PYTHON_BIN:-}" > "$REMOTE_EXEC_MARKER"',
    )

    assert completed.returncode == 0
    assert completed.marker.read_text() == (shutil.which("python3") or "")  # type: ignore[attr-defined]


def test_remote_exec_preserves_validation_lane_context_for_local_fallback(tmp_path: Path) -> None:
    completed = run_remote_exec(
        tmp_path,
        "pre-push-gate",
        "--local-fallback",
        extra_env={
            "REMOTE_EXEC_SSH_FAIL": "1",
            "LV3_VALIDATION_BASE_REF": "origin/main",
            "LV3_VALIDATION_CHANGED_FILES_JSON": '["README.md","workstreams.yaml"]',
        },
        local_command=(
            'printf "%s\\n%s" "${LV3_VALIDATION_BASE_REF:-}" '
            '"${LV3_VALIDATION_CHANGED_FILES_JSON:-}" > "$REMOTE_EXEC_MARKER"'
        ),
    )

    assert completed.returncode == 0
    recorded_base_ref, recorded_changed_files = completed.marker.read_text().splitlines()  # type: ignore[attr-defined]
    assert recorded_base_ref == "origin/main"
    assert "README.md" in json.loads(recorded_changed_files)
    assert "workstreams.yaml" in json.loads(recorded_changed_files)


def test_remote_exec_falls_back_locally_when_remote_command_fails(tmp_path: Path) -> None:
    completed = run_remote_exec(
        tmp_path,
        "remote-lint",
        "--local-fallback",
        extra_env={"REMOTE_EXEC_REMOTE_FAIL": "1"},
    )

    assert completed.returncode == 0
    assert "remote command failed" in completed.stderr
    assert completed.marker.read_text() == "local-fallback"  # type: ignore[attr-defined]


def test_remote_exec_syncs_remote_gate_status_before_local_fallback(tmp_path: Path) -> None:
    completed = run_remote_exec(
        tmp_path,
        "pre-push-gate",
        "--local-fallback",
        extra_env={
            "REMOTE_EXEC_REMOTE_FAIL": "1",
            "REMOTE_EXEC_STATUS_PAYLOAD": json.dumps(
                {
                    "status": "failed",
                    "source": "build-server",
                    "checks": [
                        {"id": "policy-validation", "status": "passed"},
                        {"id": "packer-validate", "status": "runner_unavailable"},
                    ],
                    "requested_checks": ["policy-validation", "packer-validate"],
                }
            ),
        },
        local_command=(
            "python3 - <<'PY' > \"$REMOTE_EXEC_MARKER\"\n"
            "import json\n"
            "from pathlib import Path\n"
            "payload = json.loads(Path('.local/validation-gate/last-run.json').read_text())\n"
            "print(','.join(check['id'] for check in payload['checks'] if check['status'] != 'passed'))\n"
            "PY"
        ),
    )

    assert completed.returncode == 0
    assert "remote command failed" in completed.stderr
    assert completed.marker.read_text().strip() == "packer-validate"  # type: ignore[attr-defined]


def test_check_build_server_uses_rsync_dry_run(tmp_path: Path) -> None:
    completed = run_remote_exec(tmp_path, "check-build-server")

    assert completed.returncode == 0, completed.stderr
    rsync_log = completed.rsync_log.read_text()  # type: ignore[attr-defined]
    assert "--dry-run" in rsync_log
    assert "--verbose" in rsync_log
    assert "repository-snapshot-" in rsync_log
    assert "build-server-ok" in completed.stdout
    assert REMOTE_WORKSPACE_ROOT in completed.stdout


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
        local_command='printf local-fallback > "$REMOTE_EXEC_MARKER"',
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
            "REMOTE_EXEC_WORKSPACE_ROOT": REMOTE_WORKSPACE_ROOT,
            "REMOTE_EXEC_MARKER": str(tmp_path / "marker.txt"),
            "LV3_SESSION_ID": SESSION_ID,
        }
    )
    env.update(seed_snapshot_env(tmp_path))

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


def test_remote_exec_reports_local_mesh_logout_for_headscale_proxy_failures(tmp_path: Path) -> None:
    tailscale_bin = tmp_path / "tailscale"
    make_fake_tailscale(
        tailscale_bin,
        status_output=(
            "# Health check:\n"
            "#     - You are logged out. The last login error was: fetch control key: 504 Gateway Timeout\n"
            "unexpected state: NoState\n"
        ),
    )

    completed = run_remote_exec(
        tmp_path,
        "check-build-server",
        extra_env={
            "REMOTE_EXEC_SSH_FAIL": "1",
            "REMOTE_EXEC_TAILSCALE_BIN": str(tailscale_bin),
        },
        ssh_options=["-o", "ProxyCommand=ssh ops@100.64.0.1 -W %h:%p"],
    )

    assert completed.returncode != 0
    assert "controller appears logged out of the Headscale/Tailscale mesh" in completed.stderr


def test_remote_exec_materializes_worktree_git_metadata_for_remote_workspace(tmp_path: Path) -> None:
    completed = run_remote_exec(tmp_path, "remote-lint")

    assert completed.returncode == 0, completed.stderr
    ssh_log = completed.ssh_log.read_text()  # type: ignore[attr-defined]
    rsync_log = completed.rsync_log.read_text()  # type: ignore[attr-defined]
    run_workspace_root = extract_run_workspace_root(ssh_log)
    assert ".lv3-snapshots" in ssh_log
    assert ".lv3-runs" in ssh_log
    assert "tar -xzf" in ssh_log
    assert REMOTE_WORKSPACE_ROOT in ssh_log
    assert run_workspace_root.startswith(f"{REMOTE_WORKSPACE_ROOT}/.lv3-runs/")
    assert ".git-remote" not in ssh_log
    assert ".git-remote" not in rsync_log
    assert "--delete" not in rsync_log
    assert "repository-snapshot-" in rsync_log
    assert ".lv3-snapshots" in rsync_log


def test_remote_exec_prunes_remote_workspace_by_retention_policy(tmp_path: Path) -> None:
    completed = run_remote_exec(
        tmp_path,
        "remote-lint",
        extra_env={
            "REMOTE_EXEC_SESSION_RETENTION_DAYS": "1",
            "REMOTE_EXEC_SESSION_KEEP_COUNT": "64",
            "REMOTE_EXEC_RUN_RETENTION_DAYS": "3",
            "REMOTE_EXEC_RUN_KEEP_COUNT": "12",
            "REMOTE_EXEC_SNAPSHOT_RETENTION_DAYS": "4",
            "REMOTE_EXEC_SNAPSHOT_KEEP_COUNT": "5",
        },
    )

    assert completed.returncode == 0, completed.stderr
    ssh_log = completed.ssh_log.read_text()  # type: ignore[attr-defined]
    assert "-mtime +1" in ssh_log
    assert "head -n -64" in ssh_log
    assert "head -n -12" in ssh_log
    assert "head -n -5" in ssh_log
    assert ".lv3-session-workspaces" in ssh_log
    assert ".lv3-runs" in ssh_log
    assert ".lv3-snapshots" in ssh_log


def test_remote_exec_syncs_remote_gate_status_back_to_local_checkout(tmp_path: Path) -> None:
    status_path = REPO_ROOT / ".local" / "validation-gate" / "last-run.json"
    status_path.unlink(missing_ok=True)

    completed = run_remote_exec(tmp_path, "pre-push-gate")

    assert completed.returncode == 0, completed.stderr
    assert status_path.exists()
    assert '"status":"passed"' in status_path.read_text()


def test_remote_exec_forwards_packer_related_environment_variables(tmp_path: Path) -> None:
    completed = run_remote_exec(
        tmp_path,
        "remote-lint",
        extra_env={
            "REMOTE_EXEC_VERBOSE": "1",
            "PKR_VAR_proxmox_api_token_secret": "secret-value",
            "PROXMOX_API_TOKEN_ID": "lv3-automation@pve!primary",
            "LV3_RUN_ID": "adr-0177-run",
        },
    )

    assert completed.returncode == 0, completed.stderr
    ssh_log = completed.ssh_log.read_text()  # type: ignore[attr-defined]
    assert "PKR_VAR_proxmox_api_token_secret=secret-value" in ssh_log
    assert "PROXMOX_API_TOKEN_ID=" in ssh_log
    assert "lv3-automation@pve" in ssh_log
    assert "LV3_RUN_ID=adr-0177-run" in ssh_log
    assert f"LV3_SESSION_ID={SESSION_ID}" in ssh_log
    assert "LV3_SESSION_SLUG=test-session" in ssh_log
    assert "LV3_SNAPSHOT_ID=" in ssh_log
    assert "LV3_SNAPSHOT_SOURCE_COMMIT=" in ssh_log
    assert "LV3_SNAPSHOT_BRANCH=" in ssh_log
    assert re.search(
        r"LV3_SESSION_LOCAL_ROOT=/opt/builds/proxmox_florin_server/\.lv3-session-workspaces/test-session/repo/\.lv3-runs/.+/repo/\.local/session-workspaces/test-session",
        ssh_log,
    )
