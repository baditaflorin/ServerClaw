from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "runtime-control-pool.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "runtime-control-pool.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_runtime_control_pool_playbook_covers_provisioning_substrate_namespace_migration_and_retirement() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert playbook[0]["name"] == "Ensure the runtime-control VM is provisioned on the Proxmox host"
    assert playbook[0]["hosts"] == "proxmox_hosts"
    assert [role["role"] for role in playbook[0]["roles"]] == [
        "lv3.platform.proxmox_guests",
        "lv3.platform.proxmox_network",
    ]

    assert playbook[1]["name"] == "Converge the dedicated runtime-control guest substrate"
    assert playbook[1]["hosts"] == "runtime-control-lv3"
    assert playbook[1]["vars"]["runtime_pool_substrate_pool_id"] == "runtime-control"
    pre_task_names = [task["name"] for task in playbook[1]["pre_tasks"]]
    assert "Detect whether Docker is already active before the managed runtime converge" not in pre_task_names
    assert "Stop any preexisting Docker daemon before firewall evaluation" not in pre_task_names
    assert [route["route_id"] for route in playbook[1]["vars"]["runtime_pool_substrate_routes"]] == [
        "api-gateway",
        "gitea",
        "keycloak",
        "mail-platform",
        "openfga",
        "semaphore",
        "windmill",
    ]
    route_upstreams = {
        route["route_id"]: route["upstream"] for route in playbook[1]["vars"]["runtime_pool_substrate_routes"]
    }
    assert route_upstreams == {
        "api-gateway": "{{ platform_service_topology | platform_service_url('api_gateway', 'internal') }}",
        "gitea": "{{ platform_service_topology | platform_service_url('gitea', 'internal') }}",
        "keycloak": "http://127.0.0.1:18080",
        "mail-platform": "{{ platform_service_topology.mail_platform.urls.private_api }}",
        "openfga": "{{ platform_service_topology | platform_service_url('openfga', 'internal') }}",
        "semaphore": "{{ platform_service_topology | platform_service_url('semaphore', 'internal') }}",
        "windmill": "{{ platform_service_topology | platform_service_url('windmill', 'internal') }}",
    }
    assert [role["role"] for role in playbook[1]["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.linux_access",
        "lv3.platform.docker_runtime",
        "lv3.platform.nomad_cluster_member",
        "lv3.platform.runtime_pool_substrate",
    ]
    assert playbook[1]["roles"][0]["vars"] == {
        "linux_guest_firewall_recover_missing_docker_bridge_chains": True
    }

    assert playbook[3]["name"] == "Ensure the runtime-control Nomad namespace exists"
    assert playbook[3]["hosts"] == "monitoring-lv3"
    assert [role["role"] for role in playbook[3]["roles"]] == ["lv3.platform.nomad_namespace"]

    import_playbooks = [entry["import_playbook"] for entry in playbook[4:17]]
    assert import_playbooks == [
        "step-ca.yml",
        "openbao.yml",
        "mail-platform.yml",
        "keycloak.yml",
        "openfga.yml",
        "nats-jetstream.yml",
        "gitea.yml",
        "harbor.yml",
        "semaphore.yml",
        "temporal.yml",
        "vaultwarden.yml",
        "windmill.yml",
        "api-gateway.yml",
    ]
    assert import_playbooks.index("step-ca.yml") < import_playbooks.index("openbao.yml")
    assert import_playbooks.index("openbao.yml") < import_playbooks.index("mail-platform.yml")
    openbao_import = playbook[5]
    assert openbao_import["import_playbook"] == "openbao.yml"
    assert "vars" not in openbao_import

    assert playbook[17]["name"] == "Verify the runtime-control substrate routes after the control-plane migration"
    assert playbook[17]["hosts"] == "runtime-control-lv3"
    route_urls = [
        task["ansible.builtin.uri"]["url"]
        for task in playbook[17]["tasks"]
        if "ansible.builtin.uri" in task
    ]
    assert "http://127.0.0.1:9080/api-gateway/healthz" in route_urls
    assert "http://127.0.0.1:9080/openfga/healthz" in route_urls
    dapr_task = next(
        task
        for task in playbook[17]["tasks"]
        if task["name"] == "Verify the runtime-control Dapr bridge can invoke OpenFGA through Traefik"
    )
    assert dapr_task["ansible.builtin.command"]["argv"][-1] == (
        "http://127.0.0.1:3500/v1.0/invoke/http://127.0.0.1:9080/method/openfga/healthz"
    )
    readiness_task = next(
        task
        for task in playbook[17]["tasks"]
        if task["name"] == "Record runtime-control retirement readiness on the controller"
    )
    assert readiness_task["ansible.builtin.set_fact"] == {"runtime_control_retirement_ready": True}
    assert readiness_task["delegate_to"] == "localhost"
    assert readiness_task["delegate_facts"] is True

    assert playbook[18]["name"] == "Retire the legacy control-plane copies from docker-runtime-lv3"
    assert playbook[18]["hosts"] == "docker-runtime-lv3"
    retirement_assert = next(
        task
        for task in playbook[18]["pre_tasks"]
        if task["name"] == "Assert runtime-control verification completed before retiring legacy copies"
    )
    assert retirement_assert["ansible.builtin.assert"]["that"] == [
        "hostvars['localhost'].runtime_control_retirement_ready | default(false)"
    ]
    down_task = next(
        task
        for task in playbook[18]["tasks"]
        if task["name"] == "Stop the legacy control-plane compose stacks on docker-runtime-lv3"
    )
    assert down_task["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]


def test_runtime_control_pool_service_wrapper_imports_the_root_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)

    assert wrapper == [{"import_playbook": "../runtime-control-pool.yml"}]
