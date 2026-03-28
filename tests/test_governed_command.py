from __future__ import annotations

import base64
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import governed_command as command


def test_build_execution_payload_materializes_controller_secrets(monkeypatch, tmp_path: Path) -> None:
    bootstrap_secret = tmp_path / "controller" / ".local" / "ssh" / "bootstrap.id_ed25519"
    bootstrap_secret.parent.mkdir(parents=True)
    bootstrap_secret.write_text("bootstrap-secret", encoding="utf-8")
    nats_secret = tmp_path / "controller" / ".local" / "nats" / "jetstream-admin-password.txt"
    nats_secret.parent.mkdir(parents=True)
    nats_secret.write_text("nats-secret", encoding="utf-8")
    windmill_secret = tmp_path / "controller" / ".local" / "windmill" / "superadmin-secret.txt"
    windmill_secret.parent.mkdir(parents=True)
    windmill_secret.write_text("windmill-secret", encoding="utf-8")
    runtime_repo_root = tmp_path / "runtime"
    monkeypatch.setenv("FAKE_API_TOKEN", "token-123")
    secret_paths = {
        "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/bootstrap.id_ed25519": bootstrap_secret,
        "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nats/jetstream-admin-password.txt": nats_secret,
        "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt": windmill_secret,
    }
    monkeypatch.setattr(command, "resolve_repo_local_path", lambda value: secret_paths[str(value)])

    contract = {
        "workflow_id": "open-maintenance-window",
        "inputs": [
            {
                "name": "bootstrap_ssh_private_key",
                "kind": "controller_secret",
                "required": True,
            },
            {
                "name": "api_token",
                "kind": "controller_secret",
                "required": True,
            },
            {
                "name": "nats_jetstream_admin_password",
                "kind": "controller_secret",
                "required": True,
            },
            {
                "name": "windmill_superadmin_secret",
                "kind": "controller_secret",
                "required": True,
            },
            {
                "name": "SERVICE",
                "kind": "operator_parameter",
                "required": True,
            },
        ],
        "execution": {
            "profile": "runtime",
            "timeout_seconds": 180,
        },
    }
    workflow = {"preferred_entrypoint": {"target": "open-maintenance-window"}}
    command_catalog = {
        "execution_profiles": {
            "runtime": {
                "runtime_host": "docker-runtime-lv3",
                "runtime_repo_root": str(runtime_repo_root),
                "runtime_compat_repo_root": "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server",
                "effective_user": "ops",
                "working_directory": str(runtime_repo_root),
                "env": {
                    "LV3_WINDMILL_BASE_URL": "http://127.0.0.1:8000",
                },
                "kill_mode": "mixed",
                "log_directory": str(runtime_repo_root / ".local" / "governed-command" / "logs"),
                "receipt_directory": str(runtime_repo_root / ".local" / "governed-command" / "receipts"),
            }
        }
    }
    secret_manifest = {
        "secrets": {
            "bootstrap_ssh_private_key": {
                "kind": "file",
                "path": "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/bootstrap.id_ed25519",
            },
            "api_token": {
                "kind": "env",
                "name": "FAKE_API_TOKEN",
            },
            "nats_jetstream_admin_password": {
                "kind": "file",
                "path": "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nats/jetstream-admin-password.txt",
            },
            "windmill_superadmin_secret": {
                "kind": "file",
                "path": "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt",
            },
        }
    }

    payload = command.build_execution_payload(
        command_id="open-maintenance-window",
        contract=contract,
        workflow=workflow,
        command_catalog=command_catalog,
        secret_manifest=secret_manifest,
        parameters={"SERVICE": "grafana"},
    )

    runtime_secret = runtime_repo_root / ".local" / "ssh" / "bootstrap.id_ed25519"
    runtime_nats_secret = runtime_repo_root / ".local" / "nats" / "jetstream-admin-password.txt"
    runtime_windmill_secret = runtime_repo_root / ".local" / "windmill" / "superadmin-secret.txt"
    assert payload["command"] == ["make", "open-maintenance-window"]
    assert payload["runtime_host"] == "docker-runtime-lv3"
    assert payload["env"]["BOOTSTRAP_KEY"] == str(runtime_secret)
    assert payload["env"]["LV3_NATS_PASSWORD_FILE"] == str(runtime_nats_secret)
    assert payload["env"]["LV3_WINDMILL_BASE_URL"] == "http://127.0.0.1:8000"
    assert payload["env"]["FAKE_API_TOKEN"] == "token-123"
    assert payload["env"]["SERVICE"] == "grafana"
    assert payload["timeout_seconds"] == 180
    assert payload["unit_name"].startswith("lv3-governed-open-maintenance-window-")
    assert payload["staged_files"] == [
        {
            "path": str(runtime_secret),
            "content_b64": base64.b64encode(b"bootstrap-secret").decode("utf-8"),
            "mode": "0600",
        },
        {
            "path": str(runtime_nats_secret),
            "content_b64": base64.b64encode(b"nats-secret").decode("utf-8"),
            "mode": "0600",
        },
        {
            "path": str(runtime_windmill_secret),
            "content_b64": base64.b64encode(b"windmill-secret").decode("utf-8"),
            "mode": "0600",
        }
    ]


def test_execute_governed_command_submits_runtime_payload(monkeypatch) -> None:
    runtime_root = Path("/srv/proxmox_florin_server")
    contract = {
        "workflow_id": "network-impairment-matrix",
        "inputs": [
            {
                "name": "NETWORK_IMPAIRMENT_MATRIX_ARGS",
                "kind": "operator_parameter",
                "required": False,
            }
        ],
        "execution": {"profile": "runtime", "timeout_seconds": 600},
    }
    workflow = {
        "preferred_entrypoint": {"kind": "make_target", "target": "network-impairment-matrix"}
    }
    command_catalog = {
        "execution_profiles": {
            "runtime": {
                "runtime_host": "docker-runtime-lv3",
                "runtime_repo_root": str(runtime_root),
                "runtime_compat_repo_root": "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server",
                "effective_user": "ops",
                "working_directory": str(runtime_root),
                "env": {
                    "LV3_WINDMILL_BASE_URL": "http://127.0.0.1:8000",
                },
                "kill_mode": "mixed",
                "log_directory": str(runtime_root / ".local" / "governed-command" / "logs"),
                "receipt_directory": str(runtime_root / ".local" / "governed-command" / "receipts"),
            }
        },
        "commands": {
            "network-impairment-matrix": contract,
        },
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(command, "load_catalog_context", lambda: ({}, {"workflows": {"network-impairment-matrix": workflow}}, command_catalog))
    monkeypatch.setattr(
        command,
        "evaluate_approval",
        lambda *_args, **_kwargs: {
            "approved": True,
            "workflow_id": "network-impairment-matrix",
            "entrypoint": "make network-impairment-matrix",
            "reasons": [],
        },
    )
    monkeypatch.setattr(command, "load_controller_context", lambda: {"controller": "context"})

    def fake_submit_remote_payload(controller_context, runtime_host, payload):
        captured["controller_context"] = controller_context
        captured["runtime_host"] = runtime_host
        captured["payload"] = payload
        return (
            {
                "status": "ok",
                "runtime_host": runtime_host,
                "unit_name": payload["unit_name"],
                "stdout_log": str(runtime_root / ".local" / "governed-command" / "logs" / "stdout.log"),
                "stderr_log": str(runtime_root / ".local" / "governed-command" / "logs" / "stderr.log"),
                "receipt_path": str(runtime_root / ".local" / "governed-command" / "receipts" / "receipt.json"),
                "returncode": 0,
            },
            0,
        )

    monkeypatch.setattr(command, "submit_remote_payload", fake_submit_remote_payload)

    result, outcome = command.execute_governed_command(
        command_id="network-impairment-matrix",
        requester_class="human_operator",
        approver_classes=["human_operator"],
        preflight_passed=True,
        validation_passed=True,
        receipt_planned=True,
        self_approve=False,
        break_glass=False,
        parameters={"NETWORK_IMPAIRMENT_MATRIX_ARGS": "target_class=staging --approve-risk"},
        dry_run=False,
    )

    assert outcome == "success"
    assert result["approved"] is True
    assert result["executed"] is True
    assert result["returncode"] == 0
    assert result["runtime_host"] == "docker-runtime-lv3"
    assert result["parameters"] == {
        "NETWORK_IMPAIRMENT_MATRIX_ARGS": "target_class=staging --approve-risk"
    }
    assert captured["controller_context"] == {"controller": "context"}
    assert captured["runtime_host"] == "docker-runtime-lv3"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["command"] == ["make", "network-impairment-matrix"]
    assert payload["env"]["LV3_WINDMILL_BASE_URL"] == "http://127.0.0.1:8000"
    assert payload["env"]["NETWORK_IMPAIRMENT_MATRIX_ARGS"] == "target_class=staging --approve-risk"


def test_parse_key_value_pairs_requires_name_equals_value() -> None:
    with pytest.raises(ValueError, match="must use NAME=VALUE"):
        command.parse_key_value_pairs(["missing-delimiter"])
