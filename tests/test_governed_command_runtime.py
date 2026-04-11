from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import governed_command_runtime as runtime


def test_build_systemd_run_command_sets_identity_logs_and_env(tmp_path: Path) -> None:
    stdout_log = tmp_path / "stdout.log"
    stderr_log = tmp_path / "stderr.log"
    payload = {
        "command_id": "network-impairment-matrix",
        "unit_name": "lv3-governed-network-impairment-matrix-1234",
        "effective_user": "ops",
        "working_directory": "/srv/proxmox-host_server",
        "timeout_seconds": 600,
        "kill_mode": "mixed",
        "env": {
            "BOOTSTRAP_KEY": "/srv/proxmox-host_server/.local/ssh/bootstrap.id_ed25519",
            "NETWORK_IMPAIRMENT_MATRIX_ARGS": "target_class=staging --approve-risk",
        },
        "command": ["make", "network-impairment-matrix"],
    }

    command = runtime.build_systemd_run_command(payload, stdout_log, stderr_log)

    assert command[:5] == [
        "systemd-run",
        "--quiet",
        "--wait",
        "--collect",
        "--service-type=exec",
    ]
    assert "--uid=ops" in command
    assert "--property=WorkingDirectory=/srv/proxmox-host_server" in command
    assert "--property=RuntimeMaxSec=600s" in command
    assert f"--property=StandardOutput=append:{stdout_log}" in command
    assert f"--property=StandardError=append:{stderr_log}" in command
    assert "--setenv=HOME=/home/ops" in command
    assert "--setenv=USER=ops" in command
    assert "--setenv=LOGNAME=ops" in command
    assert "--setenv=BOOTSTRAP_KEY=/srv/proxmox-host_server/.local/ssh/bootstrap.id_ed25519" in command
    assert "--setenv=NETWORK_IMPAIRMENT_MATRIX_ARGS=target_class=staging --approve-risk" in command
    assert command[-2:] == ["make", "network-impairment-matrix"]


def test_submit_stages_files_writes_receipt_and_redacts_env(monkeypatch, tmp_path: Path) -> None:
    runtime_repo_root = tmp_path / "srv" / "proxmox-host_server"
    runtime_repo_root.mkdir(parents=True)
    compat_repo_root = tmp_path / "Users" / "live" / "Documents" / "GITHUB_PROJECTS" / "proxmox-host_server"
    staged_secret = runtime_repo_root / ".local" / "ssh" / "bootstrap.id_ed25519"
    payload = {
        "command_id": "network-impairment-matrix",
        "runtime_host": "docker-runtime",
        "runtime_repo_root": str(runtime_repo_root),
        "runtime_compat_repo_root": str(compat_repo_root),
        "effective_user": "ops",
        "working_directory": str(runtime_repo_root),
        "timeout_seconds": 600,
        "kill_mode": "mixed",
        "log_directory": str(runtime_repo_root / ".local" / "governed-command" / "logs"),
        "receipt_directory": str(runtime_repo_root / ".local" / "governed-command" / "receipts"),
        "unit_name": "lv3-governed-network-impairment-matrix-1234",
        "command": ["make", "network-impairment-matrix"],
        "env": {
            "BOOTSTRAP_KEY": str(staged_secret),
            "NETWORK_IMPAIRMENT_MATRIX_ARGS": "target_class=staging --approve-risk",
        },
        "staged_files": [
            {
                "path": str(staged_secret),
                "content_b64": base64.b64encode(b"bootstrap-secret").decode("utf-8"),
                "mode": "0600",
            }
        ],
    }
    chowned_paths: list[tuple[Path, int, int]] = []

    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    monkeypatch.setattr(runtime, "resolve_account_ids", lambda _user: (1000, 1000))
    monkeypatch.setattr(
        runtime,
        "chown_path",
        lambda path, uid, gid: chowned_paths.append((Path(path), uid, gid)),
    )

    result, exit_code = runtime.submit(payload)

    assert exit_code == 0
    assert compat_repo_root.is_symlink()
    assert compat_repo_root.resolve() == runtime_repo_root.resolve()
    assert staged_secret.read_text(encoding="utf-8") == "bootstrap-secret"
    assert result["status"] == "ok"
    assert result["staged_paths"] == [str(staged_secret)]
    receipt = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["status"] == "ok"
    assert receipt["returncode"] == 0
    assert receipt["systemd_command"].count("--setenv=<redacted>") >= 5
    assert (runtime_repo_root / ".local" / "ssh", 1000, 1000) in chowned_paths
    assert (staged_secret, 1000, 1000) in chowned_paths
