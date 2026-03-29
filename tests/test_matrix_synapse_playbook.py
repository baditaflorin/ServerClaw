from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "matrix-synapse.yml"


def test_matrix_synapse_dns_stage_converges_only_the_matrix_subdomain_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[1]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "matrix.lv3.org"

    select_task = next(task for task in tasks if task.get("name") == "Select the Matrix Synapse subdomain entry")
    assert "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]

    converge_task = next(task for task in tasks if task.get("name") == "Converge the Matrix Synapse Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_name"] == "{{ selected_subdomain_record_name }}"
    assert converge_task["vars"]["hetzner_dns_record_value"] == "{{ selected_subdomain.target }}"


def test_matrix_synapse_playbook_includes_proxy_postgres_runtime_and_edge_roles() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    assert {"role": "lv3.platform.proxmox_tailscale_proxy"} in plays[0]["roles"]
    assert {"role": "lv3.platform.matrix_synapse_postgres"} in plays[2]["roles"]
    assert {"role": "lv3.platform.matrix_synapse_runtime"} in plays[3]["roles"]
    assert {"role": "lv3.platform.nginx_edge_publication"} in plays[4]["roles"]
