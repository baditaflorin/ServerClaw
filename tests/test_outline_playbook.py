from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "outline.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "outline.yml"


def test_outline_playbook_converges_only_the_outline_dns_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[0]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "wiki.lv3.org"

    select_task = next(task for task in tasks if task.get("name") == "Select the Outline subdomain entry")
    assert (
        "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]
    )

    converge_task = next(task for task in tasks if task.get("name") == "Converge the Outline Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_name"] == "{{ selected_subdomain_record_name }}"
    assert converge_task["vars"]["hetzner_dns_record_value"] == "{{ selected_subdomain.target }}"


def test_outline_playbook_bootstraps_publication_after_edge_publish() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    nginx_play = next(play for play in plays if play["name"] == "Publish Outline through the NGINX edge")
    publication_play = next(play for play in plays if play["name"] == "Bootstrap and verify Outline publication")
    publish_task = publication_play["tasks"][0]

    assert plays.index(nginx_play) < plays.index(publication_play)
    assert publication_play["hosts"] == "localhost"
    assert publication_play["connection"] == "local"
    assert publish_task["ansible.builtin.include_role"]["name"] == "lv3.platform.outline_runtime"
    assert publish_task["ansible.builtin.include_role"]["tasks_from"] == "publish.yml"


def test_outline_service_playbook_imports_the_main_outline_playbook() -> None:
    plays = yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text())
    assert plays == [{"import_playbook": "../outline.yml"}]
