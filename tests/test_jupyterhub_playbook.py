from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "jupyterhub.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "jupyterhub.yml"


def test_jupyterhub_playbook_converges_dns_runtime_edge_and_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    dns_play = plays[0]
    runtime_play = next(play for play in plays if play["name"] == "Converge JupyterHub on the Docker runtime VM")
    nginx_play = next(play for play in plays if play["name"] == "Publish JupyterHub through the NGINX edge")
    publish_play = next(play for play in plays if play["name"] == "Verify JupyterHub publication")

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "notebooks.lv3.org"

    select_task = next(task for task in dns_play["tasks"] if task.get("name") == "Select the JupyterHub subdomain entry")
    assert "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]

    assert runtime_play["roles"] == [
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.docker_runtime"},
        {"role": "lv3.platform.keycloak_runtime"},
        {"role": "lv3.platform.jupyterhub_runtime"},
    ]

    assert plays.index(nginx_play) < plays.index(publish_play)
    publish_task = publish_play["tasks"][0]
    assert publish_task["ansible.builtin.include_role"]["name"] == "lv3.platform.jupyterhub_runtime"
    assert publish_task["ansible.builtin.include_role"]["tasks_from"] == "publish.yml"


def test_jupyterhub_service_playbook_imports_the_main_jupyterhub_playbook() -> None:
    plays = yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text())
    assert plays == [{"import_playbook": "../jupyterhub.yml"}]
