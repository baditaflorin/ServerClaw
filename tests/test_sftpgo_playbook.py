from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "sftpgo.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "sftpgo.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def test_sftpgo_dns_stage_converges_only_the_files_subdomain_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[0]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "files.example.com"

    select_task = next(task for task in tasks if task.get("name") == "Select the SFTPGo subdomain entry")
    assert (
        "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]
    )

    converge_task = next(task for task in tasks if task.get("name") == "Converge the SFTPGo Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_name"] == "{{ selected_subdomain_record_name }}"
    assert converge_task["vars"]["hetzner_dns_record_value"] == "{{ selected_subdomain.target }}"


def test_sftpgo_playbook_converges_postgres_runtime_edge_and_publish_roles() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    postgres_roles = [role["role"] for role in plays[1]["roles"]]
    runtime_roles = [role["role"] for role in plays[2]["roles"]]
    edge_roles = [role["role"] for role in plays[3]["roles"]]
    publish_tasks = plays[4]["tasks"]

    assert postgres_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.postgres_vm",
        "lv3.platform.sftpgo_postgres",
    ]
    assert runtime_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.keycloak_runtime",
        "lv3.platform.sftpgo_runtime",
    ]
    assert edge_roles == ["lv3.platform.nginx_edge_publication"]
    assert plays[4]["hosts"] == "localhost"
    assert publish_tasks == [
        {
            "name": "Bootstrap and verify the SFTPGo provisioning and publication contract",
            "ansible.builtin.include_role": {
                "name": "lv3.platform.sftpgo_runtime",
                "tasks_from": "publish.yml",
            },
        }
    ]


def test_root_service_wrapper_imports_the_sftpgo_playbook() -> None:
    service = yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text())
    assert service == [{"import_playbook": "../sftpgo.yml"}]


def test_converge_sftpgo_stages_edge_static_sites_before_live_apply() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-sftpgo:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "HETZNER_DNS_API_TOKEN" in converge_block
