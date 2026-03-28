from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "rag_context_runtime" / "tasks" / "main.yml"
VERIFY_TASKS = REPO_ROOT / "roles" / "rag_context_runtime" / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "rag_context_runtime" / "templates" / "docker-compose.yml.j2"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "rag_context_runtime" / "defaults" / "main.yml"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_verify_tasks() -> list[dict]:
    return yaml.safe_load(VERIFY_TASKS.read_text())


def test_pull_task_only_targets_external_qdrant_image() -> None:
    tasks = load_tasks()
    pull_task = next(task for task in tasks if task.get("name") == "Pull the platform context images")
    assert pull_task["ansible.builtin.command"]["argv"][-2:] == ["pull", "qdrant"]


def test_compose_template_build_uses_host_network() -> None:
    assert "network: host" in COMPOSE_TEMPLATE.read_text()


def test_host_network_policy_allows_platform_context_proxy_port() -> None:
    host_vars = yaml.safe_load(
        (REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text()
    )
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    host_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "host")
    assert 8010 in host_rule["ports"]


def test_role_restores_docker_nat_chain_before_recreate() -> None:
    tasks = load_tasks()
    check_task = next(
        task for task in tasks if task.get("name") == "Check whether the Docker nat chain exists before recreating published ports"
    )
    restore_task = next(
        task for task in tasks if task.get("name") == "Restore Docker networking when the nat chain is missing"
    )
    assert check_task["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert restore_task["ansible.builtin.service"]["name"] == "docker"


def test_role_defaults_do_not_depend_on_platform_service_topology() -> None:
    defaults = ROLE_DEFAULTS.read_text()
    assert "platform_service_topology" not in defaults


def test_verify_tasks_repair_degraded_vector_index_from_controller_seed() -> None:
    tasks = load_verify_tasks()
    repair_task = next(
        task
        for task in tasks
        if task.get("name") == "Repair a degraded platform context vector index with a bounded controller-side seed rebuild"
    )
    assert repair_task["delegate_to"] == "localhost"
    assert repair_task["become"] is False
    assert "--include-path" in repair_task["ansible.builtin.command"]["cmd"]
