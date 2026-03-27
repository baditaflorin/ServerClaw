from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

from session_workspace import resolve_session_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MAIN = REPO_ROOT / "tofu" / "environments" / "production" / "main.tf"
STAGING_MAIN = REPO_ROOT / "tofu" / "environments" / "staging" / "main.tf"
PRODUCTION_TFVARS = REPO_ROOT / "tofu" / "environments" / "production" / "terraform.tfvars"
STAGING_TFVARS = REPO_ROOT / "tofu" / "environments" / "staging" / "terraform.tfvars"
HOST_VARS = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
TOKEN_SCRIPT = REPO_ROOT / "scripts" / "tofu_remote_command.py"
REMOTE_WORKSPACE_BASE = Path("/home/ops/builds/proxmox_florin_server")


def _module_block(contents: str, module_name: str) -> str:
    marker = f'module "{module_name}" {{'
    start = contents.find(marker)
    assert start >= 0, f"module {module_name} not found"
    next_module = contents.find('\nmodule "', start + len(marker))
    if next_module == -1:
        next_module = len(contents)
    window = contents[start:next_module]
    return window


def test_production_modules_match_platform_guest_catalog() -> None:
    platform = yaml.safe_load((REPO_ROOT / "inventory" / "group_vars" / "platform.yml").read_text())
    production = PRODUCTION_MAIN.read_text()

    for guest in platform["platform_guest_catalog"]["list"]:
        module_name = guest["name"].replace("-", "_")
        block = _module_block(production, module_name)
        normalized = block.replace(" ", "")

        assert f"vm_id={guest['vmid']}" in normalized
        assert f'ip_address="{guest["ipv4"]}"' in normalized
        assert f'mac_address="{guest["macaddr"]}"' in normalized


def test_staging_environment_declares_minimum_vm_set() -> None:
    staging = STAGING_MAIN.read_text()

    assert 'module "docker_runtime_staging_lv3"' in staging
    assert 'vm_id                   = 220' in staging
    assert 'module "monitoring_staging_lv3"' in staging
    assert 'vm_id                   = 240' in staging


def test_tofu_environments_target_live_proxmox_node_name() -> None:
    host_vars = yaml.safe_load(HOST_VARS.read_text())
    proxmox_node_name = host_vars["proxmox_node_name"]

    production_tfvars = PRODUCTION_TFVARS.read_text()
    staging_tfvars = STAGING_TFVARS.read_text()

    assert f'node_name               = "{proxmox_node_name}"' in production_tfvars
    assert f'template_node_name      = "{proxmox_node_name}"' in production_tfvars
    assert f'node_name               = "{proxmox_node_name}"' in staging_tfvars
    assert f'template_node_name      = "{proxmox_node_name}"' in staging_tfvars


def test_remote_command_builds_production_import_target(tmp_path: Path) -> None:
    token_file = tmp_path / "token.json"
    token_file.write_text(
        json.dumps(
            {
                "api_url": "https://proxmox.example.invalid:8006/api2/json",
                "full_token_id": "lv3-automation@pve!primary",
                "value": "secret-token",
            }
        )
    )

    completed = subprocess.run(
        [
            "python3",
            str(TOKEN_SCRIPT),
            "import",
            "production",
            "--vm",
            "nginx-lv3",
            "--token-file",
            str(token_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    command = completed.stdout.strip()
    expected_workspace = resolve_session_workspace(
        repo_root=REPO_ROOT,
        remote_workspace_base=REMOTE_WORKSPACE_BASE,
    ).remote_workspace_root
    assert expected_workspace is not None
    assert command.startswith(f"cd {expected_workspace} && ")
    assert "TOFU_DOCKER_NETWORK=host" in command
    assert "TF_VAR_proxmox_endpoint=https://proxmox.example.invalid:8006/api2/json" in command
    assert "TF_VAR_proxmox_api_token='lv3-automation@pve!primary=secret-token'" in command
    assert "./scripts/tofu_exec.sh import production module.nginx_lv3.proxmox_virtual_environment_vm.this proxmox_florin/110" in command


def test_remote_command_prefers_session_scoped_remote_workspace(tmp_path: Path) -> None:
    token_file = tmp_path / "token.json"
    token_file.write_text(
        json.dumps(
            {
                "api_url": "https://proxmox.example.invalid:8006/api2/json",
                "full_token_id": "lv3-automation@pve!primary",
                "value": "secret-token",
            }
        )
    )

    completed = subprocess.run(
        [
            "python3",
            str(TOKEN_SCRIPT),
            "plan",
            "staging",
            "--token-file",
            str(token_file),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={
            **dict(os.environ),
            "LV3_REMOTE_WORKSPACE_ROOT": "/srv/builds/proxmox_florin_server/.lv3-session-workspaces/test/repo",
        },
    )

    command = completed.stdout.strip()
    assert command.startswith("cd /srv/builds/proxmox_florin_server/.lv3-session-workspaces/test/repo && ")
    assert "./scripts/tofu_exec.sh plan staging" in command
