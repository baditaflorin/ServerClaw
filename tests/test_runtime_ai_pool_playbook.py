from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "runtime-ai-pool.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "runtime-ai-pool.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_runtime_ai_pool_playbook_covers_provisioning_substrate_namespace_migration_and_gateway_refresh() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    play_names = [play["name"] for play in playbook]

    assert play_names == [
        "Ensure the runtime-ai VM is provisioned on the Proxmox host",
        "Converge the dedicated runtime-ai guest substrate",
        "Refresh monitoring guest firewall policy after the runtime-ai peer catalog changes",
        "Ensure the runtime-ai Nomad namespace exists",
        "Converge the document-extraction services on runtime-ai-lv3",
        "Retire the legacy document-extraction copies from docker-runtime-lv3",
        "Refresh the shared API gateway after the Gotenberg move",
    ]

    assert playbook[0]["hosts"] == "proxmox_hosts"
    assert [role["role"] for role in playbook[0]["roles"]] == [
        "lv3.platform.proxmox_guests",
        "lv3.platform.proxmox_network",
    ]

    substrate_roles = [role["role"] for role in playbook[1]["roles"]]
    assert playbook[1]["hosts"] == "runtime-ai-lv3"
    pre_task_names = [task["name"] for task in playbook[1]["pre_tasks"]]
    assert "Detect whether Docker is already active before the managed runtime converge" not in pre_task_names
    assert "Stop any preexisting Docker daemon before firewall evaluation" not in pre_task_names
    assert substrate_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.linux_access",
        "lv3.platform.docker_runtime",
        "lv3.platform.nomad_cluster_member",
        "lv3.platform.runtime_pool_substrate",
    ]
    assert playbook[1]["roles"][0]["vars"] == {
        "linux_guest_firewall_recover_missing_docker_bridge_chains": True
    }

    peer_firewall_roles = [role["role"] for role in playbook[2]["roles"]]
    assert playbook[2]["hosts"] == "monitoring-lv3"
    assert peer_firewall_roles == ["lv3.platform.linux_guest_firewall"]
    assert playbook[2]["roles"][0]["vars"] == {
        "linux_guest_firewall_recover_missing_docker_bridge_chains": True
    }

    namespace_roles = [role["role"] for role in playbook[3]["roles"]]
    assert playbook[3]["hosts"] == "monitoring-lv3"
    assert namespace_roles == ["lv3.platform.nomad_namespace"]

    service_roles = [role["role"] for role in playbook[4]["roles"]]
    assert playbook[4]["hosts"] == "runtime-ai-lv3"
    assert service_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.tika_runtime",
        "lv3.platform.gotenberg_runtime",
        "lv3.platform.tesseract_ocr_runtime",
    ]
    post_task_urls = [
        task["ansible.builtin.uri"]["url"]
        for task in playbook[4]["post_tasks"]
        if "ansible.builtin.uri" in task
    ]
    assert "http://127.0.0.1:9080/tika/version" in post_task_urls
    assert "http://127.0.0.1:9080/gotenberg/health" in post_task_urls
    assert "http://127.0.0.1:9080/tesseract-ocr/healthz" in post_task_urls
    dapr_post_task = next(
        task for task in playbook[4]["post_tasks"] if task["name"] == "Verify the runtime-ai Dapr bridge can invoke Apache Tika through Traefik"
    )
    assert dapr_post_task["ansible.builtin.command"]["argv"][-1] == (
        "http://127.0.0.1:3500/v1.0/invoke/http://127.0.0.1:9080/method/tika/version"
    )
    readiness_task = next(
        task
        for task in playbook[4]["post_tasks"]
        if task["name"] == "Record runtime-ai retirement readiness on the controller"
    )
    assert readiness_task["ansible.builtin.set_fact"] == {"runtime_ai_retirement_ready": True}
    assert readiness_task["delegate_to"] == "localhost"
    assert readiness_task["delegate_facts"] is True

    assert playbook[5]["hosts"] == "docker-runtime-lv3"
    assert "roles" not in playbook[5]
    retirement_assert = next(
        task
        for task in playbook[5]["pre_tasks"]
        if task["name"] == "Assert runtime-ai verification completed before retiring legacy copies"
    )
    assert retirement_assert["ansible.builtin.assert"]["that"] == [
        "hostvars['localhost'].runtime_ai_retirement_ready | default(false)"
    ]
    down_task = next(
        task for task in playbook[5]["tasks"] if task["name"] == "Stop the legacy document-extraction compose stacks on docker-runtime-lv3"
    )
    assert down_task["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]

    assert playbook[6]["hosts"] == "docker-runtime-lv3"
    assert [role["role"] for role in playbook[6]["roles"]] == ["lv3.platform.api_gateway_runtime"]


def test_runtime_ai_pool_service_wrapper_imports_the_root_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)

    assert wrapper == [{"import_playbook": "../runtime-ai-pool.yml"}]
