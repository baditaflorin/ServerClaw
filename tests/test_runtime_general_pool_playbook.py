from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "runtime-general-pool.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "runtime-general-pool.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_runtime_general_pool_playbook_covers_provisioning_substrate_namespace_services_edge_refresh_and_retirement() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    play_names = [play["name"] for play in playbook]

    assert play_names == [
        "Ensure the runtime-general VM is provisioned on the Proxmox host",
        "Converge the dedicated runtime-general guest substrate",
        "Refresh monitoring guest firewall policy after the runtime-general peer catalog changes",
        "Ensure the runtime-general Nomad namespace exists",
        "Converge the operator and support services on runtime-general-lv3",
        "Refresh the shared NGINX edge after the runtime-general move",
        "Retire the legacy support-service copies from docker-runtime-lv3",
    ]

    assert playbook[0]["hosts"] == "proxmox_hosts"
    assert [role["role"] for role in playbook[0]["roles"]] == [
        "lv3.platform.proxmox_guests",
        "lv3.platform.proxmox_network",
    ]

    assert playbook[1]["hosts"] == "runtime-general-lv3"
    assert playbook[1]["vars"]["runtime_pool_substrate_pool_id"] == "runtime-general"
    assert [route["route_id"] for route in playbook[1]["vars"]["runtime_pool_substrate_routes"]] == [
        "uptime-kuma",
        "homepage",
        "mailpit",
    ]
    assert [role["role"] for role in playbook[1]["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.linux_access",
        "lv3.platform.docker_runtime",
        "lv3.platform.nomad_cluster_member",
        "lv3.platform.runtime_pool_substrate",
    ]

    assert playbook[3]["hosts"] == "monitoring-lv3"
    assert [role["role"] for role in playbook[3]["roles"]] == ["lv3.platform.nomad_namespace"]

    assert playbook[4]["hosts"] == "runtime-general-lv3"
    assert playbook[4]["vars"]["runtime_general_legacy_uptime_kuma_host"] == "docker-runtime-lv3"
    assert playbook[4]["vars"]["runtime_general_legacy_uptime_kuma_data_dir"] == "/opt/uptime-kuma/data"
    assert playbook[4]["vars"]["runtime_general_uptime_kuma_restore_marker"] == "/opt/uptime-kuma/.legacy-data-restored"
    pre_task_names = [task["name"] for task in playbook[4]["pre_tasks"]]
    assert "Detect whether runtime-general already restored legacy Uptime Kuma data" in pre_task_names
    assert "Detect whether legacy Uptime Kuma data exists on docker-runtime-lv3" in pre_task_names
    assert "Stop the fresh runtime-general Uptime Kuma container before restoring legacy data" in pre_task_names
    assert "Restore legacy Uptime Kuma data onto runtime-general-lv3" in pre_task_names
    assert "Record that runtime-general restored legacy Uptime Kuma data" in pre_task_names
    assert [role["role"] for role in playbook[4]["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.uptime_kuma_runtime",
        "lv3.platform.homepage_runtime",
        "lv3.platform.mailpit_runtime",
    ]
    post_task_urls = [
        task["ansible.builtin.uri"]["url"]
        for task in playbook[4]["post_tasks"]
        if "ansible.builtin.uri" in task
    ]
    assert "http://127.0.0.1:9080/uptime-kuma" in post_task_urls
    assert "http://127.0.0.1:9080/homepage" in post_task_urls
    assert "http://127.0.0.1:9080/mailpit/api/v1/info" in post_task_urls
    uptime_route_task = next(
        task
        for task in playbook[4]["post_tasks"]
        if task["name"] == "Verify the runtime-general Traefik route to Uptime Kuma"
    )
    assert uptime_route_task["ansible.builtin.uri"]["follow_redirects"] == "none"
    assert uptime_route_task["ansible.builtin.uri"]["status_code"] == [200, 302]

    dapr_post_task = next(
        task
        for task in playbook[4]["post_tasks"]
        if task["name"] == "Verify the runtime-general Dapr bridge can invoke Uptime Kuma through Traefik"
    )
    assert dapr_post_task["ansible.builtin.command"]["argv"][-1] == (
        "http://127.0.0.1:3500/v1.0/invoke/http://127.0.0.1:9080/method/uptime-kuma"
    )

    assert playbook[5]["hosts"] == "nginx-lv3"
    assert [role["role"] for role in playbook[5]["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.nginx_edge_publication",
    ]
    homepage_public_route_task = next(
        task
        for task in playbook[5]["post_tasks"]
        if task["name"] == "Verify the Homepage public route through the shared edge"
    )
    assert homepage_public_route_task["ansible.builtin.uri"]["follow_redirects"] == "none"
    assert homepage_public_route_task["ansible.builtin.uri"]["status_code"] == [200, 302, 303]
    readiness_task = next(
        task
        for task in playbook[5]["post_tasks"]
        if task["name"] == "Record runtime-general retirement readiness on the controller"
    )
    assert readiness_task["ansible.builtin.set_fact"] == {"runtime_general_retirement_ready": True}
    assert readiness_task["delegate_to"] == "localhost"
    assert readiness_task["delegate_facts"] is True

    assert playbook[6]["hosts"] == "docker-runtime-lv3"
    retirement_assert = next(
        task
        for task in playbook[6]["pre_tasks"]
        if task["name"] == "Assert runtime-general verification completed before retiring legacy copies"
    )
    assert retirement_assert["ansible.builtin.assert"]["that"] == [
        "hostvars['localhost'].runtime_general_retirement_ready | default(false)"
    ]
    down_task = next(
        task
        for task in playbook[6]["tasks"]
        if task["name"] == "Stop the legacy support-service compose stacks on docker-runtime-lv3"
    )
    assert down_task["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]


def test_runtime_general_pool_service_wrapper_imports_the_root_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)

    assert wrapper == [{"import_playbook": "../runtime-general-pool.yml"}]
