import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "nomad.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "nomad.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_nomad_playbook_covers_controller_proxy_server_clients_and_bootstrap() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    play_names = [play["name"] for play in playbook]

    assert play_names == [
        "Prepare controller-local Nomad bootstrap artifacts",
        "Converge the Proxmox firewall and Tailscale operator proxy for Nomad",
        "Converge the Nomad server on the monitoring guest",
        "Converge the Nomad clients on the runtime, runtime-ai, and build guests",
        "Bootstrap Nomad ACLs and verify repo-managed smoke jobs",
    ]

    controller_play = playbook[0]
    assert controller_play["hosts"] == "localhost"
    assert controller_play["connection"] == "local"
    include_task = controller_play["tasks"][0]
    assert include_task["ansible.builtin.include_role"]["name"] == "lv3.platform.nomad_cluster_bootstrap"
    assert include_task["ansible.builtin.include_role"]["tasks_from"] == "controller_artifacts.yml"

    host_roles = [role["role"] for role in playbook[1]["roles"]]
    assert host_roles == [
        "lv3.platform.proxmox_network",
        "lv3.platform.proxmox_tailscale_proxy",
        "lv3.platform.proxmox_security",
    ]

    server_roles = [role["role"] for role in playbook[2]["roles"]]
    assert server_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.nomad_cluster_member",
    ]

    client_roles = [role["role"] for role in playbook[3]["roles"]]
    assert "runtime-ai-lv3" in playbook[3]["hosts"]
    assert client_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.nomad_cluster_member",
    ]

    bootstrap_roles = [role["role"] for role in playbook[4]["roles"]]
    assert bootstrap_roles == ["lv3.platform.nomad_cluster_bootstrap"]


def test_nomad_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../nomad.yml"}]


def test_nomad_inventory_opens_rpc_in_both_directions_between_server_and_clients() -> None:
    host_vars = HOST_VARS_PATH.read_text()
    assert "Nomad client RPC from docker-runtime-lv3" in host_vars
    assert "Nomad client RPC from docker-build-lv3" in host_vars
    assert "Nomad client RPC from runtime-ai-lv3" in host_vars
    assert "Nomad server RPC to docker-runtime-lv3" in host_vars
    assert "Nomad server RPC to docker-build-lv3" in host_vars


def test_nomad_workflow_catalog_declares_the_converge_entrypoint() -> None:
    catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    workflow = catalog["workflows"]["converge-nomad"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-nomad",
        "command": "make converge-nomad",
    }
    assert "syntax-check-nomad" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-nomad.md"


def test_nomad_command_catalog_declares_live_change_contract() -> None:
    catalog = json.loads(COMMAND_CATALOG_PATH.read_text())
    command = catalog["commands"]["converge-nomad"]

    assert command["workflow_id"] == "converge-nomad"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True
