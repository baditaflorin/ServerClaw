from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "paperless.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "paperless.yml"


def test_paperless_playbook_composes_the_standard_service_converge_includes() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    assert [play["import_playbook"] for play in plays[:5]] == [
        "_includes/service_enabled_guard.yml",
        "_includes/dns_publication.yml",
        "_includes/postgres_preparation.yml",
        "_includes/docker_runtime_converge.yml",
        "_includes/nginx_edge_publication.yml",
    ]
    assert plays[0]["vars"] == {"service_enabled_guard_name": "paperless"}
    assert plays[1]["when"] == "service_needs_dns | default(false)"
    assert plays[2]["when"] == "service_needs_postgres | default(false)"
    assert plays[4]["when"] == "service_needs_nginx_edge | default(false)"


def test_paperless_service_vars_define_database_runtime_and_edge_convergence() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    service_vars = yaml.safe_load((REPO_ROOT / "playbooks" / "vars" / "paperless.yml").read_text())
    publication_play = plays[-1]

    assert service_vars["service_audit_name"] == "paperless"
    assert service_vars["service_dns_fqdn"] == "paperless.{{ platform_domain }}"
    assert service_vars["service_postgres_role"] == "lv3.platform.paperless_postgres"
    assert service_vars["service_runtime_roles"] == [
        "lv3.platform.docker_runtime",
        "lv3.platform.authentik_runtime",
        "lv3.platform.paperless_runtime",
        "lv3.platform.api_gateway_runtime",
    ]
    assert service_vars["service_needs_dns"] is True
    assert service_vars["service_needs_postgres"] is True
    assert service_vars["service_needs_nginx_edge"] is True

    publish_task = publication_play["tasks"][0]
    assert publication_play["hosts"] == "localhost"
    assert publication_play["connection"] == "local"
    assert publish_task["ansible.builtin.include_role"]["name"] == "lv3.platform.paperless_runtime"
    assert publish_task["ansible.builtin.include_role"]["tasks_from"] == "publish.yml"


def test_paperless_service_playbook_imports_the_main_paperless_playbook() -> None:
    plays = yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text())
    assert plays == [{"import_playbook": "../paperless.yml"}]
