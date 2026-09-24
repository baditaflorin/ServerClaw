from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "grafana_sso" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "grafana_sso" / "meta" / "argument_specs.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "grafana_sso" / "tasks" / "main.yml"
ROOT_PLAYBOOK = REPO_ROOT / "playbooks" / "services" / "grafana.yml"
COLLECTION_PLAYBOOK = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "services" / "grafana.yml"
)


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_grafana_sso_loads_the_authentik_secret_from_the_controller_local_artifact() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)
    options = load_yaml(ROLE_META)["argument_specs"]["main"]["options"]

    assert defaults["grafana_sso_client_secret_local_file"] == "{{ authentik_grafana_client_secret_local_file }}"
    assert (
        "lookup('ansible.builtin.file', grafana_sso_client_secret_local_file)" in defaults["grafana_sso_client_secret"]
    )
    assert options["grafana_sso_client_secret_local_file"]["type"] == "path"
    assert "grafana_sso_client_secret" not in options


def test_both_grafana_service_entrypoints_apply_the_authentik_sso_role() -> None:
    for playbook_path in (ROOT_PLAYBOOK, COLLECTION_PLAYBOOK):
        playbook = load_yaml(playbook_path)
        roles = [role["role"] for role in playbook[0]["roles"]]

        assert roles[-1] == "lv3.platform.grafana_sso"


def test_grafana_sso_routes_server_side_oidc_via_private_edge_and_probes_client_auth() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)
    options = load_yaml(ROLE_META)["argument_specs"]["main"]["options"]
    tasks = load_yaml(ROLE_TASKS)

    assert defaults["grafana_sso_authentik_hostname"] == "id.{{ platform_domain }}"
    assert "service_topology_get('nginx_edge')" in defaults["grafana_sso_internal_edge_ip"]
    assert "| string | trim" in defaults["grafana_sso_internal_edge_ip"]
    assert options["grafana_sso_internal_edge_ip"]["type"] == "str"
    reachability_index = next(
        index
        for index, task in enumerate(tasks)
        if task.get("name")
        == "Verify the topology-derived private edge is reachable before changing host resolution"
    )
    mapping_index = next(
        index
        for index, task in enumerate(tasks)
        if task.get("ansible.builtin.blockinfile", {}).get("path") == "/etc/hosts"
    )
    assert reachability_index < mapping_index
    assert any(
        task.get("name") == "Verify the topology-derived private edge is reachable before changing host resolution"
        and task.get("ansible.builtin.wait_for", {}).get("port") == 443
        for task in tasks
    )
    assert any(
        task.get("ansible.builtin.blockinfile", {}).get("path") == "/etc/hosts"
        and "grafana_sso_internal_edge_ip" in task["ansible.builtin.blockinfile"].get("block", "")
        for task in tasks
    )
    assert any(
        task.get("name") == "Verify Grafana client credentials are accepted by Authentik"
        and task.get("no_log") is True
        and task.get("failed_when")
        for task in tasks
    )
