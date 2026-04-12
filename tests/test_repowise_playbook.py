import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "repowise.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
COMPOSE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "repowise_runtime"
    / "templates"
    / "docker-compose.yml.j2"
)
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "repowise.yml"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_playbook_converges_repowise_on_docker_runtime() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert len(playbook) == 1
    play = playbook[0]
    assert play["hosts"] == "docker-runtime"
    roles = [role["role"] for role in play["roles"]]
    assert roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.repowise_runtime",
    ]


def test_repowise_network_policy_allows_host_edge_and_monitoring_access() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]

    host_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "host")
    nginx_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "nginx" and 7070 in rule["ports"])
    monitoring_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "monitoring" and 7070 in rule["ports"]
    )

    assert 7070 in host_rule["ports"]
    assert nginx_rule["description"] == "Reverse proxy access to the Repowise semantic search surface"
    assert monitoring_rule["description"] == "Private monitoring probes for the Repowise runtime"


def test_repowise_compose_binds_once_on_the_host_port() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert '"{{ repowise_port }}:{{ repowise_port }}"' in template
    assert '"{{ ansible_host }}:{{ repowise_port }}:{{ repowise_port }}"' not in template
    assert '"127.0.0.1:{{ repowise_port }}:{{ repowise_port }}"' not in template


def test_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)

    assert wrapper == [{"import_playbook": "../repowise.yml"}]


def test_service_catalog_points_repowise_to_the_governed_service_wrapper() -> None:
    catalog = json.loads(SERVICE_CATALOG_PATH.read_text(encoding="utf-8"))
    repowise = next(item for item in catalog["services"] if item["id"] == "repowise")

    assert repowise["deployment_surface"] == "playbooks/services/repowise.yml"
    assert repowise["runbook"] == "docs/runbooks/configure-repowise.md"


def test_ansible_execution_scopes_register_repowise_direct_playbook() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))
    direct = scopes["playbooks"]["playbooks/repowise.yml"]

    assert direct["playbook_id"] == "repowise"
    assert direct["mutation_scope"] == "host"
    assert "service:repowise" in direct["shared_surfaces"]
