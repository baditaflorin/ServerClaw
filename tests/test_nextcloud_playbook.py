from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "nextcloud.yml"


def test_nextcloud_dns_stage_converges_only_the_nextcloud_subdomain_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[0]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "cloud.lv3.org"

    select_task = next(task for task in tasks if task.get("name") == "Select the Nextcloud subdomain entry")
    assert "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]

    converge_task = next(task for task in tasks if task.get("name") == "Converge the Nextcloud Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_name"] == "{{ selected_subdomain_record_name }}"
    assert converge_task["vars"]["hetzner_dns_record_value"] == "{{ selected_subdomain.target }}"


def test_nextcloud_playbook_converges_postgres_runtime_and_edge_roles() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    postgres_roles = [role["role"] for role in plays[1]["roles"]]
    runtime_roles = [role["role"] for role in plays[2]["roles"]]
    edge_roles = [role["role"] for role in plays[3]["roles"]]

    assert postgres_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.postgres_vm",
        "lv3.platform.nextcloud_postgres",
    ]
    assert runtime_roles == [
        "lv3.platform.docker_runtime",
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.nextcloud_runtime",
    ]
    assert edge_roles == ["lv3.platform.nginx_edge_publication"]
