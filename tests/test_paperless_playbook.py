from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "paperless.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "paperless.yml"


def test_paperless_playbook_converges_only_the_paperless_dns_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[0]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "paperless.example.com"

    select_task = next(task for task in tasks if task.get("name") == "Select the Paperless subdomain entry")
    assert (
        "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]
    )

    converge_task = next(task for task in tasks if task.get("name") == "Converge the Paperless Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_name"] == "{{ selected_subdomain_record_name }}"
    assert converge_task["vars"]["hetzner_dns_record_value"] == "{{ selected_subdomain.target }}"


def test_paperless_playbook_converges_database_runtime_api_gateway_and_edge_then_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    docker_play = next(play for play in plays if play["name"] == "Converge Paperless on the Docker runtime VM")
    nginx_play = next(play for play in plays if play["name"] == "Publish Paperless through the NGINX edge")
    publication_play = next(play for play in plays if play["name"] == "Verify Paperless publication end to end")

    roles = [role["role"] for role in docker_play["roles"]]
    assert roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.keycloak_runtime",
        "lv3.platform.paperless_runtime",
        "lv3.platform.api_gateway_runtime",
    ]
    assert plays.index(nginx_play) < plays.index(publication_play)

    publish_task = publication_play["tasks"][0]
    assert publication_play["hosts"] == "localhost"
    assert publication_play["connection"] == "local"
    assert publish_task["ansible.builtin.include_role"]["name"] == "lv3.platform.paperless_runtime"
    assert publish_task["ansible.builtin.include_role"]["tasks_from"] == "publish.yml"


def test_paperless_service_playbook_imports_the_main_paperless_playbook() -> None:
    plays = yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text())
    assert plays == [{"import_playbook": "../paperless.yml"}]
