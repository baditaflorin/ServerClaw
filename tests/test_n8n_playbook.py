from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "n8n.yml"


def test_n8n_dns_stage_converges_only_the_n8n_subdomain_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[0]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "n8n.example.com"

    select_task = next(task for task in tasks if task.get("name") == "Select the n8n subdomain entry")
    assert (
        "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]
    )

    converge_task = next(task for task in tasks if task.get("name") == "Converge the n8n Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_name"] == "{{ selected_subdomain_record_name }}"
    assert converge_task["vars"]["hetzner_dns_record_value"] == "{{ selected_subdomain.target }}"

    task_names = {task["name"] for task in tasks}
    assert "Ensure Hetzner DNS records are present" not in task_names


def test_n8n_edge_publication_skips_unrelated_static_site_syncs() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    edge_play = next(play for play in plays if {"role": "lv3.platform.nginx_edge_publication"} in play.get("roles", []))

    assert edge_play["vars"]["public_edge_sync_generated_static_dirs"] is False
